/** Manage an isolated, persistent local AgentDb stack for this checkout. */
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const state = join(root, '.state', 'agentdb');
const [command, ...args] = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
const saved = existsSync(join(state, 'stack.json')) ? JSON.parse(readFileSync(join(state, 'stack.json'), 'utf8')) : null;
const source = resolve(args.includes('--agentdb-root') ? option('--agentdb-root') : process.env.AGENTDB_ROOT || saved?.source || 'C:/cogit/cogit-core/agent-db');
const load = relative => import(pathToFileURL(join(source, relative)).href);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const json = file => JSON.parse(readFileSync(file, 'utf8'));
function save(name, value) {
  mkdirSync(state, { recursive: true });
  const file = join(state, name), temp = file + '.tmp';
  writeFileSync(temp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  renameSync(temp, file);
}

async function main() {
  const { ensureEnv, readEnvFile, composeDir, standaloneFile } = await load('scripts/hndb.mjs');
  const { runCommand, dockerBin, preflightDocker } = await load('scripts/compose.mjs');
  mkdirSync(state, { recursive: true });
  let stamp = saved;
  const envPath = join(state, '.env');
  if (!stamp) {
    if (command !== 'start') throw new Error('Start the local stack first.');
    stamp = { source, project: 'commerce-' + randomBytes(8).toString('hex') };
    const admin = randomBytes(32).toString('hex'), client = randomBytes(32).toString('hex');
    ensureEnv(false, 'agentdb', { path: envPath, overrides: {
      COMPOSE_PROJECT_NAME: stamp.project, AGENTDB_COMPOSE_OWNER: stamp.project,
      AGENTDB_CLEANUP_PERMITTED: 'false', AGENTDB_DEPLOYMENT_MODE: 'test',
      AGENTDB_PG_VOLUME: stamp.project + '-pg', AGENTDB_OBJECT_VOLUME: stamp.project + '-objects', AGENTDB_PG_NETWORK: stamp.project + '-network',
      POSTGRES_HOST_PORT: '15432', AGENTDB_API_HOST_PORT: '18080', AGENTDB_API_PROBE_HOST_PORT: '18081',
      AGENTDB_COORDINATOR_PROBE_HOST_PORT: '18083', AGENTDB_API_METRICS_HOST_PORT: '18084', AGENTDB_COORDINATOR_METRICS_HOST_PORT: '18085',
      AGENTDB_TEST_IDENTITY_TOKENS: admin + ':agentdb.local:platform-admin,' + client + ':agentdb.local:commerce-client',
      LOCAL_COMMERCE_ADMIN_TOKEN: admin, LOCAL_COMMERCE_CLIENT_TOKEN: client, LOCAL_COMMERCE_LOOP_KEY: randomBytes(32).toString('hex'),
    }});
    writeFileSync(join(state, 'persistent.yaml'), 'services:\n  postgres:\n    restart: unless-stopped\n  minio:\n    restart: unless-stopped\n  api:\n    restart: unless-stopped\n  coordinator:\n    restart: unless-stopped\n');
    save('stack.json', stamp);
  }
  if (stamp.source !== source) throw new Error('This stack is bound to a different AgentDb source checkout.');
  const env = readEnvFile(envPath);
  const processEnv = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(AGENTDB_|POSTGRES_|MINIO_|COMPOSE_)/i.test(k)));
  const compose = async (tail, stdin) => runCommand(dockerBin(processEnv), ['compose', '-p', stamp.project, '--env-file', envPath, '-f', standaloneFile, '-f', join(state, 'persistent.yaml'), ...tail], { cwd: composeDir, env: processEnv, ...(stdin ? {stdin} : {}), timeoutMs: 600000 });
  const apiUrl = 'http://127.0.0.1:' + env.AGENTDB_API_HOST_PORT;
  const post = async (path, body, key, admin = true) => {
    const response = await fetch(apiUrl + path, { method: 'POST', headers: {
      'content-type': 'application/json', authorization: 'Bearer ' + env[admin ? 'LOCAL_COMMERCE_ADMIN_TOKEN' : 'LOCAL_COMMERCE_CLIENT_TOKEN'],
      'idempotency-key': 'commerce-' + key, 'x-agentdb-correlation-id': randomUUID(),
    }, body: JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(20000) });
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      throw new Error(`${path}: HTTP ${response.status} ${failure.error?.code || ''}`);
    }
    return response.json();
  };
  if (command === 'start') {
    await preflightDocker(processEnv);
    const {stdout} = await runCommand(dockerBin(processEnv), ['context','inspect','--format','{{.Endpoints.docker.Host}}'], {env:processEnv,timeoutMs:15000});
    if (!/^(npipe|unix):\/\//.test(stdout.trim())) throw new Error('This command requires a local Docker engine.');
    console.log('Starting the isolated PostgreSQL, object store, AgentDb API and coordinator.');
    await compose(['up', '-d', '--build', '--wait']);
    const response = await fetch(apiUrl + '/version', {signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('AgentDb version endpoint did not pass.');
    save('ready.json', { apiUrl, postgresPort: Number(env.POSTGRES_HOST_PORT), version: await response.json() });
    console.log(JSON.stringify({apiUrl, project:stamp.project, ready:true}));
  } else if (command === 'status') {
    const {stdout} = await compose(['ps']); console.log(stdout);
  } else if (command === 'stop') {
    await compose(['stop']); console.log('Stopped this checkout’s AgentDb services; volumes retained.');
  } else if (command === 'restart') {
    await compose(['restart','postgres','minio','api','coordinator']);
    await compose(['up','-d','--wait']); console.log('Restarted AgentDb with existing volumes.');
  } else if (command === 'deploy') {
    if (!args.includes('--plan')) throw new Error('deploy requires --plan from prepare_agentdb.py');
    const plan = json(resolve(option('--plan')));
    const {initializeApplication, planModule, applyModule} = await load('packages/deployment/dist/index.js');
    const admin = (path, body, key) => post('/v1/admin' + path, body, key);
    const tenant = await admin('/tenants',{slug:'commerce',displayName:'Agentic Commerce local demo'},'tenant');
    await admin('/tenants/'+tenant.tenantId+'/activate',{expectedVersion:tenant.version},'tenant-activate');
    const principal = async(subject,kind) => (await admin('/principals/resolve',{issuer:'agentdb.local',subject,kind,displayName:subject},'principal-'+subject)).principalId;
    const operator = await principal('commerce-client','user');
    const worker = await principal('commerce-worker','service');
    await admin('/memberships',{tenantId:tenant.tenantId,principalId:operator,role:'tenant_admin'},'operator-membership');
    const publisher = await admin('/publishers',{slug:'commerce',displayName:'Agentic Commerce'},'publisher');
    const routes = {};
    for (const [name,agent] of Object.entries(plan.agents)) {
      const prepared=json(join(agent.cohort,'prepared.json'));
      if (prepared.executableSha256!==sha(readFileSync(join(agent.cohort,'executable.json'))) || prepared.manifestSha256!==sha(readFileSync(join(agent.cohort,'cogit.yaml')))) throw new Error('Prepared cohort bytes changed: '+name);
      const agentPrincipalId=await principal(name,'agent');
      const definition=await admin('/agent-definitions',{publisherId:publisher.publisherId,stableKey:name,displayName:name},name+'-definition');
      const hashes={executableSha256:prepared.executableSha256,manifestSha256:prepared.manifestSha256};
      const version=await admin('/agent-definitions/'+definition.definitionId+'/versions',{versionLabel:'1.0.0',...hashes},name+'-version-'+hashes.executableSha256);
      const pool=await admin('/pools',{definitionId:definition.definitionId,versionId:version.versionId,name:name+'-pool'},name+'-pool-'+version.versionId);
      await admin('/pools/'+pool.poolId+'/workers',{principalId:worker},name+'-worker-'+pool.poolId);
      const installation=await admin('/installations',{tenantId:tenant.tenantId,definitionId:definition.definitionId,versionId:version.versionId,agentPrincipalId},name+'-installation-'+version.versionId);
      const deployment=await admin('/deployments',{tenantId:tenant.tenantId,installationId:installation.installationId,poolId:pool.poolId},name+'-deployment-'+version.versionId);
      routes[name]={tenantId:tenant.tenantId,installationId:installation.installationId,definitionId:definition.definitionId,versionId:version.versionId,poolId:pool.poolId,deploymentId:deployment.deploymentId,agentPrincipalId,...hashes,cohort:agent.cohort,project:agent.project};
    }
    let text=readFileSync(envPath,'utf8');
    text=text.replace(/^AGENTDB_WORKER_PRINCIPAL_ID=.*$/m,'AGENTDB_WORKER_PRINCIPAL_ID='+worker);
    writeFileSync(envPath,text,{mode:0o600});
    await compose(['up','-d','--no-build','--wait','api','coordinator']);
    const connectionString=`postgresql://agentdb_migrator:${env.AGENTDB_PASSWORD_agentdb_migrator}@127.0.0.1:${env.POSTGRES_HOST_PORT}/agentdb`;
    const config={connectionString};
    await initializeApplication(config,{applicationKey:'agentic-commerce',mode:'attach',tenantId:tenant.tenantId,operatorPrincipalId:operator});
    const approvals=Object.entries(plan.modules).map(([moduleKey,bundle])=>({moduleKey,artifactSha256:bundle.approvedArtifactSha256}));
    for (const [name,agent] of Object.entries(plan.agents)) {
      for (const requirement of agent.requirements) {
        const bundle=plan.modules[requirement.module_key];
        if (!bundle) throw new Error('Missing module bundle: '+requirement.module_key);
        const request={tenantId:tenant.tenantId,installationId:routes[name].installationId,...bundle,requirements:agent.requirements};
        const pending=await planModule(config,request,approvals);
        await applyModule(config,{...request,expectedRevision:pending.baseRevision},approvals);
      }
    }
    for(const moduleKey of ['cogit-messaging','cogit-finance-catalog','cogit-finance-deals']) {
      await post('/v1/modules/'+encodeURIComponent(moduleKey)+'/settings',{expectedRevision:0,values:{operator_principal_id:operator,escrow_installation_id:routes['cogit-finance'].installationId}},'settings-'+moduleKey,false);
    }
    // Deterministic agents never call a model, but the runtime still pins a local
    // accounting version on admitted work. No external provider is configured.
    const price='commerce-disabled-v1';
    await compose(['exec','-T','postgres','psql','-X','-v','ON_ERROR_STOP=1','-U','postgres','-d','agentdb'],
      "SET ROLE agentdb_owner; INSERT INTO core.model_price_versions(price_version,currency,rates,content_sha256,reviewed_by) VALUES ('"+price+"','USD','{\"runtime:disabled\":{\"inputPerMillion\":\"1\",\"outputPerMillion\":\"1\"}}'::jsonb,decode(repeat('00',32),'hex'),'local-commerce') ON CONFLICT DO NOTHING;\n");
    for (const [name,route] of Object.entries(routes)) await post('/v1/agent-settings',{installationId:route.installationId,settingsKey:'model-spend',schemaKey:'model.spend.v1',expectedVersion:0,values:{currency:'USD',priceVersion:price,maxRunCost:'0.01'}},'spend-'+name,false);
    save('routes.json',{apiUrl,tenantId:tenant.tenantId,operatorPrincipalId:operator,routes});
    console.log(JSON.stringify({apiUrl,tenantId:tenant.tenantId,agents:Object.keys(routes),modules:Object.keys(plan.modules)}));
  } else {
    throw new Error('Usage: node scripts/agentdb_stack.mjs start|status|stop|restart|deploy [--agentdb-root PATH] [--plan FILE]');
  }
}

main().catch(error => { console.error(error.message); process.exitCode=1; });
