import { spawnSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { cp, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

type Response = { status: number; body: Record<string, unknown> };
type CohortStack = {
  ids: Record<string, string>;
  ownerQuery: (sql: string, values?: unknown[]) => Promise<{ rows: Record<string, unknown>[] }>;
  post: (path: string, body: unknown, headers: Record<string, string>) => Promise<Response>;
};

export type PreparedCohort = {
  directory: string;
  root: string;
  manifestPath: string;
  executableSha256: string;
  manifestSha256: string;
};

export type PublishedCohort = {
  installationId: string;
  versionId: string;
  deploymentId: string;
  poolId: string;
  receiptPath: string;
  manifestPath: string;
};

function hash(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

function field(value: unknown, name: string): string {
  if (typeof value !== 'string' || value.length === 0) throw new Error(`Missing ${name}`);
  return value;
}

function platformHeaders(key: string): Record<string, string> {
  return {
    authorization: 'Bearer platform-admin',
    'x-agentdb-correlation-id': randomUUID(),
    'idempotency-key': key,
  };
}

export async function copyPreparedCohort(source: string, label: string,
  expectedEntrypoint: string): Promise<PreparedCohort> {
  const root = await mkdtemp(join(tmpdir(), `template-${label}-cohort-`));
  const directory = join(root, 'cohort');
  try {
    await cp(resolve(source), directory, { recursive: true, errorOnExist: true, force: false });
    if (existsSync(join(directory, 'receipt.json'))) {
      throw new Error('Supply an unsigned prepared cohort; receipts are bound per published route');
    }
    const manifestPath = join(directory, 'cogit.yaml');
    const descriptor = await readFile(join(directory, 'executable.json'));
    const manifest = await readFile(manifestPath);
    const prepared = JSON.parse(await readFile(join(directory, 'prepared.json'), 'utf8'));
    const executable = JSON.parse(descriptor.toString('utf8'));
    const executableSha256 = hash(descriptor);
    const manifestSha256 = hash(manifest);
    if (prepared.contractVersion !== 'cogit.worker-cohort-prepared.v1'
        || prepared.executableSha256 !== executableSha256
        || prepared.manifestSha256 !== manifestSha256
        || prepared.entrypoint !== executable.entrypoint
        || executable.contractVersion !== 'cogit.worker-executable.v1'
        || executable.entrypoint !== expectedEntrypoint
        || !Array.isArray(executable.wheels)
        || executable.wheels.length !== 5) {
      throw new Error('Prepared cohort metadata differs from its artifact bytes');
    }
    const distributions = new Set<string>();
    for (const wheel of executable.wheels) {
      if (typeof wheel.path !== 'string' || !/^wheels\/[A-Za-z0-9_.+-]+\.whl$/.test(wheel.path)) {
        throw new Error('Prepared cohort contains an invalid wheel path');
      }
      if (hash(await readFile(join(directory, wheel.path))) !== wheel.sha256) {
        throw new Error('Prepared cohort wheel hash mismatch');
      }
      distributions.add(field(wheel.distribution, 'wheel distribution'));
    }
    if (distributions.size !== 5 || !['reference-cogit-agent', 'cogit-runtime',
      'cogit-agent-sdk', 'agentdb-client', 'cogit-tool-core'].every((name) => distributions.has(name))) {
      throw new Error('Prepared cohort does not contain the exact agent/framework closure');
    }
    return { root, directory, manifestPath, executableSha256, manifestSha256 };
  } catch (error) {
    await rm(root, { recursive: true, force: true });
    throw error;
  }
}

export async function removePreparedCohort(cohort: PreparedCohort): Promise<void> {
  await rm(cohort.root, { recursive: true, force: true });
}

export async function publishPreparedCohort(
  stack: CohortStack,
  cohort: PreparedCohort,
  python: string,
  templateRoot: string,
  key: string,
): Promise<PublishedCohort> {
  const tenantId = field(stack.ids['tenantA'], 'tenant ID');
  const oldInstallationId = field(stack.ids['installationA'], 'seed installation ID');
  const agentPrincipalId = field(stack.ids['agent'], 'agent principal ID');
  const workerPrincipalId = field(stack.ids['worker2'], 'worker principal ID');
  const current = await stack.ownerQuery(
    `SELECT d.deployment_id, d.definition_id
       FROM core.agent_deployments d
      WHERE d.tenant_id=$1::uuid AND d.installation_id=$2::uuid AND d.status='active'`,
    [tenantId, oldInstallationId],
  );
  if (current.rows.length !== 1) throw new Error('Expected one active seeded deployment');
  const old = current.rows[0]!;
  const definitionId = field(old['definition_id'], 'seed definition ID');
  const oldDeploymentId = field(old['deployment_id'], 'seed deployment ID');
  // This fixture's unused placeholder follows the authenticated deployment
  // lifecycle. Busy-work rejection must stop setup, never trigger owner DML.
  async function transition(action: 'retain' | 'retire', status: 'retained' | 'disabled'): Promise<void> {
    const path = `/v1/admin/installations/${oldInstallationId}/${action}`;
    const result = await stack.post(path, { tenantId, deploymentId: oldDeploymentId },
      platformHeaders(`${key}-${action}`));
    if (result.status !== 200 || result.body['installationId'] !== oldInstallationId
        || result.body['deploymentId'] !== oldDeploymentId || result.body['status'] !== status) {
      throw new Error(`Seed cohort ${action} rejected: ${result.status} ${JSON.stringify(result.body)}`);
    }
  }
  await transition('retain', 'retained');
  await transition('retire', 'disabled');

  async function posted(path: string, body: unknown, suffix: string): Promise<Record<string, unknown>> {
    const result = await stack.post(path, body, platformHeaders(`${key}-${suffix}`));
    if (result.status !== 201) throw new Error(`${path} returned ${result.status}: ${JSON.stringify(result.body)}`);
    return result.body;
  }
  const version = await posted(`/v1/admin/agent-definitions/${definitionId}/versions`, {
    versionLabel: '2.0.0',
    executableSha256: cohort.executableSha256,
    manifestSha256: cohort.manifestSha256,
  }, 'version');
  const versionId = field(version['versionId'], 'published version ID');
  const pool = await posted('/v1/admin/pools', {
    definitionId, versionId, name: 'template-cohort',
  }, 'pool');
  const poolId = field(pool['poolId'], 'published pool ID');
  await posted(`/v1/admin/pools/${poolId}/workers`, { principalId: workerPrincipalId }, 'worker');
  const installation = await posted('/v1/admin/installations', {
    tenantId, definitionId, versionId, agentPrincipalId,
  }, 'installation');
  const installationId = field(installation['installationId'], 'published installation ID');
  const deployment = await posted('/v1/admin/deployments', {
    tenantId, installationId, poolId,
  }, 'deployment');
  const deploymentId = field(deployment['deploymentId'], 'published deployment ID');

  const command = [
    '-I', '-B', resolve(templateRoot, 'scripts/worker_cohort.py'), 'receipt',
    '--cohort', cohort.directory,
    '--tenant-id', tenantId,
    '--installation-id', installationId,
    '--definition-id', definitionId,
    '--version-id', versionId,
    '--deployment-id', deploymentId,
    '--pool-id', poolId,
    '--agent-principal-id', agentPrincipalId,
    '--published-executable-sha256', cohort.executableSha256,
    '--published-manifest-sha256', cohort.manifestSha256,
  ];
  const bound = spawnSync(python, command, {
    cwd: templateRoot,
    env: { ...process.env, PYTHONPATH: '' },
    encoding: 'utf8',
    timeout: 30000,
  });
  if (bound.status !== 0) {
    throw new Error(`Cohort receipt binding failed: ${bound.error ?? bound.stderr}`);
  }
  return {
    installationId,
    versionId,
    deploymentId,
    poolId,
    receiptPath: join(cohort.directory, 'receipt.json'),
    manifestPath: cohort.manifestPath,
  };
}
