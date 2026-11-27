import { spawn, spawnSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { request as httpRequest } from 'node:http';
import { createServer as createHttpsServer } from 'node:https';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyModule, initializeApplication } from '@a10-agentdb/packages/deployment/src/index.ts';
import { parseClaimResource } from '@a10-agentdb/packages/contracts/src/index.ts';
import { manifestDigest, parseModuleManifest } from '@a10-agentdb/packages/module-kit/src/index.ts';
import { finalizeArtifactViaApi } from '@a10-agentdb/tests/workspace/artifact-finalize-required.helpers.ts';
import { freeResourcePort } from '@a10-agentdb/tests/workspace/resource-abi-fixture.helpers.ts';
import { startQueryWaitStack } from '@a10-agentdb/tests/workspace/query-wait-stack.helpers.ts';
import { copyPreparedCohort, publishPreparedCohort, removePreparedCohort } from './worker_cohort.ts';

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} for the installed A10 worker proof`);
  return value;
}

const templateRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const bundlePath = resolve(requiredEnv('COGIT_A10_BUNDLE_PATH'));
const digest = requiredEnv('COGIT_A10_BUNDLE_DIGEST');
const moduleKey = 'cogit.reference-case-agent';
const cli = resolve(requiredEnv('COGIT_A10_RUNTIME_CLI'));
const python = resolve(dirname(cli), process.platform === 'win32' ? 'python.exe' : 'python');
const cohortSource = resolve(requiredEnv('COGIT_A10_COHORT_DIR'));
const manifestPath = resolve(cohortSource, 'cogit.yaml');
const wheelPath = resolve(requiredEnv('COGIT_A10_WHEEL_PATH'));
const wheelSha256 = requiredEnv('COGIT_A10_WHEEL_SHA256');
const image = process.env['COGIT_A10_IMAGE']?.trim();

function docker(args: string[], timeout = 30000): string {
  const result = spawnSync('docker', args, { encoding: 'utf8', timeout, windowsHide: true });
  if (result.status !== 0) {
    throw new Error(`Docker ${args[0]} failed: ${result.error ?? (result.stderr || result.stdout)}`);
  }
  return result.stdout.trim();
}

async function dockerAsync(args: string[], timeout = 30000): Promise<string> {
  return await new Promise<string>((accept, reject) => {
    const child = spawn('docker', args, { windowsHide: true });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (bytes) => { stdout += String(bytes); });
    child.stderr.on('data', (bytes) => { stderr += String(bytes); });
    child.on('error', reject);
    const timer = setTimeout(() => { child.kill(); reject(new Error(`Docker ${args[0]} timed out`)); }, timeout);
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) reject(new Error(`Docker ${args[0]} failed: ${stderr || stdout}`));
      else accept(stdout.trim());
    });
  });
}

function dockerLogs(name: string): string {
  const result = spawnSync('docker', ['logs', name], { encoding: 'utf8', timeout: 30000, windowsHide: true });
  return `${result.stdout}${result.stderr}`.trim();
}

async function startImageTlsProxy(apiBaseUrl: string): Promise<{ url: string; caPath: string;
  stop: () => Promise<void> }> {
  const certPath = resolve(requiredEnv('COGIT_A10_IMAGE_TLS_CERT_PATH'));
  const keyPath = resolve(requiredEnv('COGIT_A10_IMAGE_TLS_KEY_PATH'));
  const caPath = resolve(requiredEnv('COGIT_A10_IMAGE_TLS_CA_PATH'));
  const backend = new URL(apiBaseUrl);
  if (backend.protocol !== 'http:' || backend.hostname !== '127.0.0.1') {
    throw new Error('A10 TLS proxy only forwards to the fixture loopback AgentDb API');
  }
  const server = createHttpsServer({ cert: await readFile(certPath), key: await readFile(keyPath) },
    (request, response) => {
      if (!request.url?.startsWith('/') || request.url.startsWith('//')) {
        response.writeHead(400).end();
        return;
      }
      const upstream = httpRequest({ hostname: backend.hostname, port: backend.port,
        path: request.url, method: request.method,
        headers: { ...request.headers, host: backend.host } }, (result) => {
        response.writeHead(result.statusCode ?? 502, result.headers);
        result.pipe(response);
      });
      upstream.on('error', (error) => {
        if (response.headersSent) response.destroy(error);
        else response.writeHead(502).end();
      });
      request.pipe(upstream);
    });
  const port = await new Promise<number>((accept, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject);
      const address = server.address();
      if (!address || typeof address === 'string') reject(new Error('A10 TLS proxy has no TCP port'));
      else accept(address.port);
    });
  });
  return { url: `https://host.docker.internal:${port}`, caPath,
    stop: async () => {
      server.closeAllConnections();
      await new Promise<void>((accept, reject) => server.close((error) => error ? reject(error) : accept()));
    } };
}

async function preflightImageWorker(imageRef: string, project: string, url: string, caPath: string,
  executableSha256: string, manifestSha256: string,
  preparedSha256: string): Promise<{ network: string; url: string; imageId: string }> {
  const connection = { network: `${project}_net`, url };
  const imageId = docker(['image', 'inspect', '--format', '{{.Id}}', imageRef]);
  const probeName = `${project}-image-probe`;
  const ownership = randomUUID();
  const probe = `
import hashlib, httpx, json, sys, urllib3
from pathlib import Path
url = sys.argv[1]
try:
    response = urllib3.PoolManager().request('GET', url, retries=False,
        timeout=urllib3.Timeout(connect=5, read=5))
    httpx_response = httpx.get(url, timeout=5)
    if response.status >= 500 or httpx_response.status_code >= 500:
        raise ValueError(f'upstream HTTP status {response.status}, {httpx_response.status_code}')
except Exception as error:
    print(f'A10_TLS_ERROR: {error}', file=sys.stderr)
    sys.exit(12)
root = Path('/app/worker-cohort')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
executable = json.loads((root / 'executable.json').read_text())
print(json.dumps({
    'executable': digest(root / 'executable.json'),
    'manifest': digest(root / 'cogit.yaml'),
    'prepared': digest(root / 'prepared.json'),
    'wheelsVerified': all(digest(root / wheel['path']) == wheel['sha256']
                          for wheel in executable['wheels']),
}))
`;
  let output: string;
  try {
    output = await dockerAsync(['run', '--rm', '--name', probeName,
      '--label', `org.cogit.a10.proof=${ownership}`,
      '--network', connection.network,
      '--mount', `type=bind,source=${caPath},target=/tmp/a10-ca.pem,readonly`,
      '-e', 'SSL_CERT_FILE=/tmp/a10-ca.pem', '--entrypoint', 'python', imageId,
      '-I', '-B', '-c', probe, connection.url], 30000);
  } catch (error) {
    // A killed Docker client can leave its --rm container running.
    let probeId: string | undefined;
    try {
      const inspected = JSON.parse(docker(['inspect', '--format', '{{json .}}', probeName]));
      if (inspected?.Config?.Labels?.['org.cogit.a10.proof'] === ownership
          && /^[0-9a-f]{64}$/.test(inspected.Id)) {
        probeId = inspected.Id;
      }
    } catch { /* the task-owned probe already exited */ }
    if (probeId) docker(['rm', '-f', probeId]);
    if (String(error).includes('A10_TLS_ERROR:')) {
      throw new Error(`A10 image cannot verify the host TLS proxy at ${connection.url} from Docker network `
        + `${connection.network}. Check Docker Desktop host.docker.internal and the mounted test CA. ${error}`);
    }
    throw new Error(`A10 image preflight failed before publication: ${error}`);
  }
  const actual = JSON.parse(output);
  if (actual.executable !== executableSha256 || actual.manifest !== manifestSha256
      || actual.prepared !== preparedSha256
      || actual.wheelsVerified !== true) {
    throw new Error('A10 image cohort differs from the published, image-extracted cohort');
  }
  return { ...connection, imageId };
}

async function imageWorkerUntilSettled(config: { imageRef: string; project: string; network: string;
  url: string; caPath: string; poolId: string; installationId: string; approvalDeciderId: string;
  receiptPath: string; runId: string;
  ownerQuery: (sql: string, values?: unknown[]) => Promise<{ rows: Record<string, unknown>[] }> }) {
  const name = `${config.project}-image-worker`;
  const ownership = randomUUID();
  let containerId: string | undefined;
  try {
    const started = docker(['run', '-d', '--no-healthcheck', '--name', name,
      '--label', `org.cogit.a10.proof=${ownership}`, '--network', config.network,
      '--mount', `type=bind,source=${config.receiptPath},target=/app/worker-cohort/receipt.json,readonly`,
      '--mount', `type=bind,source=${config.caPath},target=/tmp/a10-ca.pem,readonly`,
      '-e', 'COGIT_DEV_MODE=0', '-e', 'COGIT_AGENT_API_KEY=',
      '-e', 'SSL_CERT_FILE=/tmp/a10-ca.pem',
      '-e', `COGIT_AGENTDB_URL=${config.url}`, '-e', 'COGIT_AGENTDB_API_VERSION=0.1.0',
      '-e', `COGIT_AGENTDB_POOL_ID=${config.poolId}`,
      '-e', `COGIT_AGENTDB_INSTALLATION_ID=${config.installationId}`,
      '-e', `COGIT_AGENTDB_APPROVAL_DECIDER_ID=${config.approvalDeciderId}`,
      '-e', 'COGIT_AGENTDB_WORKER_TOKEN=worker-secret-2',
      '-e', 'COGIT_AGENTDB_COHORT_RECEIPT=/app/worker-cohort/receipt.json',
      '-e', 'DATABASE_URL=', '-e', 'PYTHONPATH=',
      '--entrypoint', 'sh', config.imageRef, '/app/scripts/start_database_worker.sh']);
    if (!/^[0-9a-f]{64}$/.test(started)) throw new Error(`Docker returned an invalid container ID: ${started}`);
    containerId = started;
    const deadline = Date.now() + 90000;
    while (Date.now() < deadline) {
      const result = await config.ownerQuery('SELECT lifecycle FROM core.runs WHERE run_id=$1', [config.runId]);
      const lifecycle = result.rows[0]?.['lifecycle'];
      if (lifecycle === 'succeeded') {
        const cmdline = docker(['exec', containerId, 'python', '-I', '-B', '-c',
          "from pathlib import Path; print(Path('/proc/1/cmdline').read_bytes().decode().replace('\\0', ' '))"]);
        if (!/python(?:3)?(?:\.\d+)? -I(?: -B)? -m cogit_runtime work(?: |$)/.test(cmdline)) {
          throw new Error(`Image worker did not exec isolated Runtime: ${cmdline}`);
        }
        return { mode: 'image', cmdline };
      }
      if (lifecycle === 'failed' || lifecycle === 'cancelled') {
        throw new Error(`Image worker run ${lifecycle}: ${dockerLogs(containerId)}`);
      }
      const running = docker(['inspect', '--format', '{{.State.Running}}', containerId]);
      if (running !== 'true') throw new Error(`Image worker exited: ${dockerLogs(containerId)}`);
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 1000));
    }
    throw new Error(`Image worker timed out: ${dockerLogs(containerId)}`);
  } finally {
    if (!containerId) {
      // Docker may have created the container before reporting a start failure.
      // A name collision is never proof of ownership.
      try {
        const labels = JSON.parse(docker(['inspect', '--format', '{{json .Config.Labels}}', name]));
        if (labels?.['org.cogit.a10.proof'] === ownership) {
          containerId = docker(['inspect', '--format', '{{.Id}}', name]);
        }
      } catch { /* no task-owned container exists */ }
    }
    if (containerId) {
      try { docker(['rm', '-f', containerId]); } catch (error) {
        throw new Error(`Could not remove task-owned image worker ${containerId}: ${error}`);
      }
    }
  }
}

async function workerOnce(config: { url: string; poolId: string; installationId: string;
  approvalDeciderId: string; manifestPath: string; receiptPath: string }) {
  const env = { ...process.env,
    COGIT_DEV_MODE: '0',
    COGIT_AGENT_API_KEY: '',
    COGIT_AGENTDB_URL: config.url,
    COGIT_AGENTDB_API_VERSION: '0.1.0',
    COGIT_AGENTDB_POOL_ID: config.poolId,
    COGIT_AGENTDB_INSTALLATION_ID: config.installationId,
    COGIT_AGENTDB_APPROVAL_DECIDER_ID: config.approvalDeciderId,
    COGIT_AGENTDB_WORKER_TOKEN: 'worker-secret-2',
    COGIT_AGENTDB_COHORT_RECEIPT: config.receiptPath,
    DATABASE_URL: '',
    PYTHONPATH: '',
  };
  return await new Promise<{ code: number | null; stdout: string; stderr: string }>((done, fail) => {
    const child = spawn(python, ['-I', '-B', '-m', 'cogit_runtime', 'work',
      '--manifest', config.manifestPath, '--once'], {
      cwd: dirname(bundlePath), env, windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (bytes) => { stdout += String(bytes); });
    child.stderr.on('data', (bytes) => { stderr += String(bytes); });
    child.on('error', fail);
    const timer = setTimeout(() => { child.kill(); fail(new Error('worker timed out')); }, 90000);
    child.on('close', (code) => { clearTimeout(timer); done({ code, stdout, stderr }); });
  });
}

async function verifyResolutionExports(stack: Awaited<ReturnType<typeof startQueryWaitStack>>,
  installationId: string, poolId: string, version: string, key: string) {
  const text = 'Verify the installed resolution exports.';
  const artifact = await finalizeArtifactViaApi(stack, text, `${key}-resolution-input`, { mediaType: 'text/plain' });
  const admitted = await stack.post('/v1/queries', { installationId,
    input: { text, sha256: artifact.sha256 } }, stack.ada(`${key}-resolution-admit`));
  expect(admitted.status, JSON.stringify(admitted.body)).toBe(202);
  await stack.publishPending();
  const response = await stack.post('/v1/worker/claims', { poolId }, stack.worker('worker-2', randomUUID()));
  expect(response.status, JSON.stringify(response.body)).toBe(201);
  const claim = parseClaimResource(response.body);
  const attempt = `/v1/worker/attempts/${claim.attemptId}`;
  const begun = await stack.post(`${attempt}/executions`, { generation: claim.generation },
    stack.workerAttempt(claim.token, randomUUID(), 'worker-2'));
  expect(begun.status, JSON.stringify(begun.body)).toBe(201);
  const pins = { generation: claim.generation, executionId: begun.body['executionId'],
    moduleVersion: version, artifactSha256: digest, exportVersion: '1.0.0' };
  const scope = `${attempt}/modules/${moduleKey}`;
  const apply = (resolution: string) => stack.post(`${scope}/commands/resolutions.apply`, {
    ...pins, contractId: `${moduleKey}.resolutions.apply.v1`, workerRequestId: randomUUID(),
    input: { case_id: 'resolution-proof', resolution, request_key: 'stable-resolution-key' },
  }, stack.workerAttempt(claim.token, randomUUID(), 'worker-2'));
  const exact = 'Keep Unicode café 東京\n  and whitespace.';
  const first = await apply(exact);
  expect(first.status, JSON.stringify(first.body)).toBe(200);
  expect(first.body).toEqual({ applied: true, already_applied: false });
  const replay = await apply(exact);
  expect(replay.status, JSON.stringify(replay.body)).toBe(200);
  expect(replay.body).toEqual({ applied: true, already_applied: true });
  expect((await apply('different text')).status).toBeGreaterThanOrEqual(400);
  const query = { ...pins, contractId: `${moduleKey}.resolutions.list.v1`,
    input: { case_id: 'resolution-proof' } };
  const denied = await stack.post(`${scope}/queries/resolutions.list`, query,
    stack.bev(`${key}-unrelated-tenant`));
  expect(denied.status).toBeGreaterThanOrEqual(400);
  const readback = await stack.post(`${scope}/queries/resolutions.list`, query,
    stack.workerAttempt(claim.token, randomUUID(), 'worker-2'));
  expect(readback.status, JSON.stringify(readback.body)).toBe(200);
  expect(readback.body).toEqual({ case_id: 'resolution-proof', resolutions: [exact] });
}

test.each(['canonical-input.txt', 'json-looking-input.txt'])(
  'real AgentDb claim preserves %s and commits the exact public artifact', async (inputFixture: string): Promise<void> => {
  const wheel = await readFile(wheelPath);
  expect(createHash('sha256').update(wheel).digest('hex')).toBe(wheelSha256);
  const executable = JSON.parse(await readFile(resolve(cohortSource, 'executable.json'), 'utf8'));
  const pins: { wheelSha256: Record<string, string> } = JSON.parse(
    await readFile(resolve(templateRoot, 'vendor/wheels/cohort.json'), 'utf8'));
  const frameworkWheels = Object.entries(pins.wheelSha256).filter(([filename]) =>
    /^(agentdb_client|cogit_agent_sdk|cogit_runtime|cogit_tool_core)-/.test(filename));
  expect(frameworkWheels).toHaveLength(4);
  const reviewed = new Set(['agentdb-client', 'cogit-agent-sdk', 'cogit-runtime', 'cogit-tool-core']);
  for (const [filename, sha256] of frameworkWheels) {
    const identity = /^([a-z0-9_]+)-(\d+\.\d+\.\d+)-py3-none-any\.whl$/.exec(filename);
    if (!identity) throw new Error(`Invalid reviewed framework wheel filename: ${filename}`);
    const distribution = identity[1]!.replaceAll('_', '-');
    if (!reviewed.delete(distribution)) throw new Error(`Unexpected reviewed framework wheel: ${distribution}`);
    const member = executable.wheels.find((item: { distribution: string }) => item.distribution === distribution);
    expect(member).toMatchObject({ distribution, version: identity[2],
      path: `wheels/${filename}`, sha256 });
    const sourceWheel = await readFile(resolve(templateRoot, 'vendor/wheels', filename));
    expect(createHash('sha256').update(sourceWheel).digest('hex')).toBe(sha256);
  }
  expect(reviewed.size).toBe(0);
  const agentWheel = executable.wheels.find((item: { distribution: string }) => item.distribution === 'reference-cogit-agent');
  expect(agentWheel).toBeDefined();
  expect(resolve(cohortSource, agentWheel.path)).toBe(wheelPath);
  expect(agentWheel.sha256).toBe(wheelSha256);
  const probe = spawnSync(python, ['-I', '-B', '-c', `
import json, sys
from importlib.metadata import version
from pathlib import Path
from zipfile import ZipFile
import reference_agent
from reference_agent.database_bundle import load_database_bundle
root = Path(reference_agent.__file__).parent
members = ('database_example.py', 'public/root-result.v1.schema.json',
           'database/manifest.json', 'database/historical/module-1.0.0/manifest.json')
with ZipFile(sys.argv[1]) as wheel:
    same = all((root / member).read_bytes() == wheel.read('reference_agent/' + member)
               for member in members)
print(json.dumps({'path': str(root), 'version': version('reference-cogit-agent'),
                  'digest': load_database_bundle()[1], 'wheel_parity': same}))
`, wheelPath], { cwd: dirname(bundlePath), env: { ...process.env, PYTHONPATH: '' }, encoding: 'utf8' });
  expect(probe.status, probe.stderr).toBe(0);
  const installedPackage = JSON.parse(probe.stdout.trim());
  expect(installedPackage.path.toLowerCase()).toContain('site-packages');
  expect(wheelPath).toContain(`reference_cogit_agent-${installedPackage.version}-`);
  expect(agentWheel.version).toBe(installedPackage.version);
  expect(installedPackage.digest).toBe(digest);
  expect(installedPackage.wheel_parity).toBe(true);
  expect(await readFile(manifestPath, 'utf8')).toContain(digest);
  const text = await readFile(resolve(templateRoot, 'tests/fixtures/a10', inputFixture), 'utf8');
  const project = `a10w${randomUUID().slice(0, 8)}`;
  const port = await freeResourcePort();
  const adminPort = await freeResourcePort();
  const cohort = await copyPreparedCohort(cohortSource, 'a10', 'reference_agent.agent:ReferenceAgent');
  let stack: Awaited<ReturnType<typeof startQueryWaitStack>>;
  try {
    stack = await startQueryWaitStack({ project, port, adminPort });
  } catch (error) {
    await removePreparedCohort(cohort);
    throw error;
  }
  let tlsProxy: Awaited<ReturnType<typeof startImageTlsProxy>> | undefined;
  try {
    tlsProxy = image ? await startImageTlsProxy(stack.apiBaseUrl()) : undefined;
    const imageConnection = image
      ? await preflightImageWorker(image, project, tlsProxy!.url, tlsProxy!.caPath,
        cohort.executableSha256, cohort.manifestSha256,
        createHash('sha256').update(await readFile(resolve(cohort.directory, 'prepared.json'))).digest('hex'))
      : undefined;
    const published = await publishPreparedCohort(stack, cohort,
      python, templateRoot, `${project}-${inputFixture}`);
    const manifest = parseModuleManifest(JSON.parse(await readFile(resolve(bundlePath, 'manifest.json'), 'utf8')));
    expect(manifestDigest(manifest)).toBe(digest);
    const exports = manifest.exports.filter((item) =>
      ['requests.put', 'requests.get', 'resolutions.apply', 'resolutions.list'].includes(item.key))
      .map((item) => ({ kind: item.kind, key: item.key, export_version: item.version, contract_id: item.contractId }));
    expect(exports).toHaveLength(4);
    const tenantId = stack.ids['tenantA']!;
    const approvalDeciderId = stack.ids['approver']!;
    await stack.ownerQuery(
      "INSERT INTO core.capability_grants(tenant_id,grant_id,principal_id,capability) VALUES($1,gen_random_uuid(),$2,'human.decide')",
      [tenantId, approvalDeciderId],
    );
    const decider = await stack.ownerQuery('SELECT core.human_decider_authorized($1,$2) AS authorized',
      [tenantId, approvalDeciderId]);
    expect(decider.rows).toEqual([{ authorized: true }]);
    const installationId = published.installationId;
    const config = { ...stack.apiConnection, user: 'agentdb_migrator' };
    await initializeApplication(config, { applicationKey: `test.${project}`, mode: 'attach', tenantId,
      operatorPrincipalId: stack.ids['ada']! });
    const installed = await applyModule(config, { tenantId, installationId, bundlePath,
      approvedArtifactSha256: digest, requirements: [{ module_key: moduleKey,
        version: manifest.version, artifact_sha256: digest, exports }] },
      [{ moduleKey, artifactSha256: digest }]);
    expect(installed.status).toBe('installed');
    const poolId = published.poolId;
    expect(poolId).toMatch(/^[0-9a-f-]{36}$/);
    const readiness = await stack.get(`/v1/worker/module-readiness?installationId=${installationId}`,
      stack.worker('worker-2', `${project}-readiness`));
    expect(readiness.status, JSON.stringify(readiness.body)).toBe(200);
    expect(readiness.body).toMatchObject({ ready: true, installationId,
      agentVersionId: published.versionId, deploymentId: published.deploymentId,
      poolId, cohortStatus: 'active' });
    const expectedRequestId = 'text-' + createHash('sha256').update(tenantId + '\0' + text).digest('hex');
    const expectedRoot = Buffer.from(JSON.stringify({ outcome: 'completed', requestId: expectedRequestId,
      revision: 1, schemaVersion: 'reference-request-result.v1', status: 'open' }) + '\n', 'utf8');
    const expectedHash = createHash('sha256').update(expectedRoot).digest('hex');
    const input = await finalizeArtifactViaApi(stack, text, `${project}-input`, { mediaType: 'text/plain' });
    const admitted = await stack.post('/v1/queries', { installationId,
      input: { text, sha256: input.sha256 } }, stack.ada(`${project}-admit`));
    expect(admitted.status, JSON.stringify(admitted.body)).toBe(202);
    await stack.publishPending();
    const runId = String(admitted.body['runId']);
    let workerEvidence: Record<string, unknown>;
    if (image && imageConnection) {
      const worker = await imageWorkerUntilSettled({ imageRef: imageConnection.imageId, project,
        network: imageConnection.network, url: imageConnection.url, caPath: tlsProxy!.caPath, poolId,
        installationId, approvalDeciderId, receiptPath: published.receiptPath, runId,
        ownerQuery: stack.ownerQuery });
      workerEvidence = { mode: worker.mode, image, imageId: imageConnection.imageId,
        network: imageConnection.network, apiUrl: imageConnection.url, cmdline: worker.cmdline };
      console.log('a10-image-worker', JSON.stringify(workerEvidence));
    } else {
      const worker = await workerOnce({ url: stack.apiBaseUrl(), poolId, installationId, approvalDeciderId,
        manifestPath: published.manifestPath, receiptPath: published.receiptPath });
      const launchError = worker.stderr.replace(/worker-secret(?:-2)?/g, '[redacted]').slice(-4000);
      expect(worker.code, launchError).toBe(0);
      expect(worker.stdout).toContain('claimed=1 completed=1 failed=0');
      workerEvidence = { mode: 'installed-host', stdout: worker.stdout };
      console.log('a10-worker', JSON.stringify(worker));
    }
    const rowTable = `tenant_t_${tenantId.replaceAll('-', '')}.reference_agent_requests`;
    const rows = await stack.ownerQuery(`SELECT object_id,request_id,description,status,revision FROM ${rowTable} WHERE request_id=$1`, [expectedRequestId]);
    expect(rows.rows).toHaveLength(1);
    expect(rows.rows[0]['description']).toBe(text);
    expect(rows.rows[0]['status']).toBe('open');
    expect(rows.rows[0]['revision']).toBe(1);
    const receipts = await stack.ownerQuery("SELECT worker_request_id FROM core.module_worker_receipts WHERE tenant_id=$1 AND run_id=$2 AND module_key=$3 AND export_key='requests.put'", [tenantId, runId, moduleKey]);
    expect(receipts.rows).toHaveLength(1);
    const roots = await stack.ownerQuery(`SELECT a.artifact_id::text AS id, encode(a.sha256,'hex') AS hash,
      a.byte_length, a.media_type, a.classification, l.rel FROM core.artifacts a
      JOIN core.artifact_links l ON l.tenant_id=a.tenant_id AND l.artifact_id=a.artifact_id
      WHERE l.object_id=$1::uuid AND a.sha256=decode($2,'hex')`, [runId, expectedHash]);
    expect(roots.rows).toHaveLength(1);
    expect(roots.rows[0]['hash']).toBe(expectedHash);
    expect(Number(roots.rows[0]['byte_length'])).toBe(expectedRoot.length);
    expect(roots.rows[0]['media_type']).toBe('application/json');
    expect(roots.rows[0]['rel']).toBe('evidence');
    const rootId = String(roots.rows[0]['id']);
    const response = await fetch(`${stack.apiBaseUrl()}/v1/artifacts/${rootId}/bytes`, {
      headers: stack.ada(`${project}-read-root`),
    });
    expect(response.status).toBe(200);
    const actualRoot = Buffer.from(await response.arrayBuffer());
    expect(actualRoot).toEqual(expectedRoot);
    const run = await stack.ownerQuery('SELECT lifecycle,result_artifact_id::text AS result_id FROM core.runs WHERE run_id=$1', [runId]);
    expect(run.rows).toHaveLength(1);
    expect(run.rows[0]['lifecycle']).toBe('succeeded');
    const runtimeResultId = String(run.rows[0]['result_id']);
    expect(runtimeResultId).not.toBe(rootId);
    const runtimeResponse = await fetch(`${stack.apiBaseUrl()}/v1/artifacts/${runtimeResultId}/bytes`, {
      headers: stack.ada(`${project}-read-runtime-result`),
    });
    expect(runtimeResponse.status).toBe(200);
    const runtimeResult = JSON.parse(Buffer.from(await runtimeResponse.arrayBuffer()).toString('utf8'));
    const persist = runtimeResult.output.steps.find((step: { id: string }) => step.id === 'persist');
    expect(persist.output.root_artifact_id).toBe(rootId);
    expect(persist.output.root_sha256).toBe(expectedHash);
    if (inputFixture === 'canonical-input.txt') {
      await verifyResolutionExports(stack, installationId, poolId, manifest.version, project);
    }
    const evidence = { project, inputFixture, runId, worker: workerEvidence, expectedRequestId, rootId,
      rootSha256: expectedHash, rootBytes: actualRoot.toString('utf8'),
      runtimeResultArtifactId: runtimeResultId, rows: rows.rows };
    console.log('a10-proof', JSON.stringify(evidence));
    if (process.env['COGIT_A10_EVIDENCE_PATH']) {
      const evidencePath = process.env['COGIT_A10_EVIDENCE_PATH'];
      const selectedPath = inputFixture === 'canonical-input.txt' ? evidencePath : `${evidencePath}.json-looking.json`;
      await writeFile(selectedPath, `${JSON.stringify(evidence, null, 2)}\n`);
    }
  } finally {
    try {
      await tlsProxy?.stop();
    } finally {
      try {
        await stack.stop();
      } finally {
        await removePreparedCohort(cohort);
      }
    }
  }
}, 300000);
