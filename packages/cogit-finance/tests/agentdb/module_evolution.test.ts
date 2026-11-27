import { spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  applyModule,
  initializeApplication,
  planModule,
} from "@d08-agentdb/packages/deployment/src/index.ts";
import { loadModuleBundle } from "@d08-agentdb/packages/module-kit/src/index.ts";
import { freeResourcePort } from "@d08-agentdb/tests/workspace/resource-abi-fixture.helpers.ts";
import { startQueryWaitStack } from "@d08-agentdb/tests/workspace/query-wait-stack.helpers.ts";

const templateRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleKey = "cogit.reference-case-agent";
const oldResource = "reference-case-agent-requests";
const nextResource = "reference-case-agent-requests-next";
const digests = {
  base: "5543cf86e831965e014f910fb8936fe5ea3881c8754f740f1a32c2e69c88008e",
  v2: "2a3a4a6c2a7259b522d020b4dd17e3617d4ecf69472a12029e59ec5e0f65cee4",
  v3: "211392dcc7c38ff2b3c89d7b7c2bd8f74d4ca3059eaaa0dc8a3b69be51e3f8a8",
};

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} for the installed D08 module proof`);
  return value;
}

function python(pythonPath: string, args: string[]): string {
  const run = spawnSync(pythonPath, ["-I", ...args], {
    cwd: templateRoot,
    env: { ...process.env, PYTHONPATH: "" },
    encoding: "utf8",
    maxBuffer: 2 * 1024 * 1024,
  });
  expect(run.status, run.stderr || run.error?.message).toBe(0);
  return run.stdout.trim();
}

async function installedBase(
  pythonPath: string,
  wheelPath: string,
): Promise<string> {
  const probe = python(pythonPath, [
    "-c",
    `
import json, sys
from importlib.metadata import version
from pathlib import Path
from zipfile import ZipFile
import reference_agent
from reference_agent.database_bundle import load_database_bundle

package = Path(reference_agent.__file__).resolve().parent
prefix = Path(sys.prefix).resolve()
with ZipFile(sys.argv[1]) as wheel:
    members = [name for name in wheel.namelist()
               if name.startswith('reference_agent/database/') and not name.endswith('/')]
    parity = bool(members) and all(
        (package / name.removeprefix('reference_agent/')).read_bytes() == wheel.read(name)
        for name in members)
print(json.dumps({'package': str(package), 'prefix': str(prefix),
                  'version': version('reference-cogit-agent'),
                  'digest': load_database_bundle()[1], 'wheelParity': parity,
                  'installedInPrefix': package.is_relative_to(prefix)}))
`,
    wheelPath,
  ]);
  const installed = JSON.parse(probe) as {
    package: string;
    prefix: string;
    version: string;
    digest: string;
    wheelParity: boolean;
    installedInPrefix: boolean;
  };
  expect(installed.version).toBe("0.1.12");
  expect(installed.package.toLowerCase()).toContain("site-packages");
  expect(installed.installedInPrefix).toBe(true);
  expect(installed.digest).toBe(digests.base);
  expect(installed.wheelParity).toBe(true);
  return resolve(installed.package, "database");
}

function buildSuccessor(
  pythonPath: string,
  basePath: string,
  outputPath: string,
  retired: boolean,
): string {
  return python(pythonPath, [
    resolve(templateRoot, "tests/fixtures/d08/build_evolution.py"),
    basePath,
    outputPath,
    ...(retired ? ["--retired"] : []),
  ]);
}

test("installed Template module retains old identity, isolates tenants, and denies rollback", async () => {
  const pythonPath = resolve(requiredEnv("COGIT_D08_PYTHON"));
  const wheelPath = resolve(requiredEnv("COGIT_D08_AGENT_WHEEL"));
  const wheelHash = requiredEnv("COGIT_D08_AGENT_WHEEL_SHA256");
  expect(
    createHash("sha256")
      .update(await readFile(wheelPath))
      .digest("hex"),
  ).toBe(wheelHash);
  const basePath = await installedBase(pythonPath, wheelPath);
  const scratch = await mkdtemp(join(tmpdir(), "template-d08-"));
  let stack: Awaited<ReturnType<typeof startQueryWaitStack>> | undefined;
  try {
    const v2Path = join(scratch, "v2");
    const v3Path = join(scratch, "v3");
    expect(buildSuccessor(pythonPath, basePath, v2Path, false)).toBe(
      digests.v2,
    );
    expect(buildSuccessor(pythonPath, basePath, v3Path, true)).toBe(digests.v3);
    const [base, v2, v3] = await Promise.all([
      loadModuleBundle(basePath, digests.base),
      loadModuleBundle(v2Path, digests.v2),
      loadModuleBundle(v3Path, digests.v3),
    ]);
    expect([
      base.manifest.version,
      v2.manifest.version,
      v3.manifest.version,
    ]).toEqual(["1.1.0", "2.0.0", "3.0.0"]);
    const project = `d08w${randomUUID().slice(0, 8)}`;
    const port = await freeResourcePort();
    let adminPort = await freeResourcePort();
    while (adminPort === port) adminPort = await freeResourcePort();
    stack = await startQueryWaitStack({ project, port, adminPort });
    const schema = await stack.ownerQuery(
      "SELECT max(sequence)::int AS head FROM core.schema_migrations",
    );
    const schemaHead = Number(schema.rows[0]?.["head"]);
    expect([193, 194]).toContain(schemaHead);
    if (process.env["COGIT_D08_REQUIRED_SCHEMA_HEAD"]) {
      expect(schemaHead).toBe(Number(process.env["COGIT_D08_REQUIRED_SCHEMA_HEAD"]));
    }
    const tenantA = stack.ids["tenantA"]!;
    const tenantB = stack.ids["tenantB"]!;
    const config = { ...stack.apiConnection, user: "agentdb_migrator" };
    await initializeApplication(config, {
      applicationKey: `test.${project}.a`,
      mode: "attach",
      tenantId: tenantA,
      operatorPrincipalId: stack.ids["ada"]!,
    });
    await initializeApplication(config, {
      applicationKey: `test.${project}.b`,
      mode: "attach",
      tenantId: tenantB,
      operatorPrincipalId: stack.ids["bev"]!,
    });
    const request = (
      tenantId: string,
      path: string,
      digest: string,
      expectedRevision: number,
    ) => ({
      tenantId,
      bundlePath: path,
      approvedArtifactSha256: digest,
      expectedRevision,
    });
    const approved = (digest: string) => [
      { moduleKey, artifactSha256: digest },
    ];
    for (const tenantId of [tenantA, tenantB]) {
      const first = await applyModule(
        config,
        request(tenantId, basePath, digests.base, 0),
        approved(digests.base),
      );
      expect(first).toMatchObject({
        status: "installed",
        moduleVersion: "1.1.0",
        revision: 1,
      });
    }
    const naturalKey = `d08-${project}`;
    const createOld = (tenant: "a" | "b") =>
      stack!.post(
        `/v1/data/${oldResource}`,
        { requestId: naturalKey, description: `Original ${tenant}` },
        tenant === "a"
          ? stack!.ada(`${project}-old-a`)
          : stack!.bev(`${project}-old-b`),
      );
    const [oldA, oldB] = await Promise.all([createOld("a"), createOld("b")]);
    expect(oldA.status, JSON.stringify(oldA.body)).toBe(201);
    expect(oldB.status, JSON.stringify(oldB.body)).toBe(201);
    const oldAId = String(oldA.body["objectId"]);
    const oldBId = String(oldB.body["objectId"]);
    expect(oldAId).not.toBe(oldBId);
    const before = await stack.ownerQuery(
      "SELECT object_id::text AS object_id,type_key,type_version FROM core.objects WHERE tenant_id=$1 AND object_id=$2",
      [tenantA, oldAId],
    );
    expect(before.rows).toEqual([
      {
        object_id: oldAId,
        type_key: "reference_agent_request",
        type_version: 1,
      },
    ]);

    for (const tenantId of [tenantA, tenantB]) {
      const plan = await planModule(
        config,
        request(tenantId, v2Path, digests.v2, 1),
        approved(digests.v2),
      );
      expect(plan).toMatchObject({
        baseVersion: "1.1.0",
        moduleVersion: "2.0.0",
        status: "ready",
      });
      const installed = await applyModule(
        config,
        request(tenantId, v2Path, digests.v2, 1),
        approved(digests.v2),
      );
      expect(installed).toMatchObject({
        status: "installed",
        moduleVersion: "2.0.0",
        revision: 2,
      });
    }
    const oldRead = await stack.get(
      `/v1/data/${oldResource}/${oldAId}`,
      stack.ada(`${project}-old-read`),
    );
    expect(oldRead.status, JSON.stringify(oldRead.body)).toBe(200);
    expect(oldRead.body["objectId"]).toBe(oldAId);
    const oldList = await stack.get(
      `/v1/data/${oldResource}`,
      stack.ada(`${project}-old-list`),
    );
    expect(oldList.status).toBe(200);
    expect(
      (oldList.body["items"] as Record<string, unknown>[]).some(
        (item) => item["objectId"] === oldAId,
      ),
    ).toBe(true);
    const deniedOldWrite = await stack.post(
      `/v1/data/${oldResource}`,
      { requestId: `${naturalKey}-denied`, description: "No old writes" },
      stack.ada(`${project}-old-write-denied`),
    );
    expect(deniedOldWrite.status).toBe(404);
    const createNext = (tenant: "a" | "b") =>
      stack!.post(
        `/v1/data/${nextResource}`,
        {
          requestId: naturalKey,
          description: `Successor ${tenant}`,
          detail: "A distinct type",
        },
        tenant === "a"
          ? stack!.ada(`${project}-next-a`)
          : stack!.bev(`${project}-next-b`),
      );
    const [nextA, nextB] = await Promise.all([
      createNext("a"),
      createNext("b"),
    ]);
    expect(nextA.status, JSON.stringify(nextA.body)).toBe(201);
    expect(nextB.status, JSON.stringify(nextB.body)).toBe(201);
    const nextAId = String(nextA.body["objectId"]);
    const nextBId = String(nextB.body["objectId"]);
    expect(new Set([oldAId, oldBId, nextAId, nextBId]).size).toBe(4);
    const nextRead = await stack.get(
      `/v1/data/${nextResource}/${nextAId}`,
      stack.ada(`${project}-next-read`),
    );
    expect(nextRead.status, JSON.stringify(nextRead.body)).toBe(200);
    expect(nextRead.body).toEqual(nextA.body);
    const nextList = await stack.get(
      `/v1/data/${nextResource}`,
      stack.ada(`${project}-next-list`),
    );
    expect(nextList.status).toBe(200);
    expect(
      (nextList.body["items"] as Record<string, unknown>[]).some(
        (item) => item["objectId"] === nextAId,
      ),
    ).toBe(true);
    const after = await stack.ownerQuery(
      "SELECT object_id::text AS object_id,type_key,type_version FROM core.objects WHERE tenant_id=$1 AND object_id IN ($2,$3) ORDER BY object_id",
      [tenantA, oldAId, nextAId],
    );
    expect(after.rows).toEqual(
      expect.arrayContaining([
        {
          object_id: oldAId,
          type_key: "reference_agent_request",
          type_version: 1,
        },
        {
          object_id: nextAId,
          type_key: "reference_agent_request_next",
          type_version: 1,
        },
      ]),
    );
    for (const [resource, id] of [
      [oldResource, oldAId],
      [nextResource, nextAId],
    ]) {
      const denied = await stack.get(
        `/v1/data/${resource}/${id}`,
        stack.bev(`${project}-cross-${resource}`),
      );
      expect(denied.status).toBe(404);
    }
    await expect(
      applyModule(
        config,
        request(tenantA, basePath, digests.base, 2),
        approved(digests.base),
      ),
    ).rejects.toMatchObject({
      code: "validation_failed",
      detail: "unsupported upgrade base",
    });
    const afterRollback = await stack.ownerQuery(
      "SELECT version,revision FROM core.tenant_modules WHERE tenant_id=$1 AND module_key=$2",
      [tenantA, moduleKey],
    );
    expect(afterRollback.rows).toEqual([{ version: "2.0.0", revision: "2" }]);
    expect(
      (
        await stack.get(
          `/v1/data/${nextResource}/${nextAId}`,
          stack.ada(`${project}-next-after-rollback`),
        )
      ).status,
    ).toBe(200);

    const retired = await applyModule(
      config,
      request(tenantA, v3Path, digests.v3, 2),
      approved(digests.v3),
    );
    expect(retired).toMatchObject({
      status: "installed",
      moduleVersion: "3.0.0",
      revision: 3,
    });
    expect(
      (
        await stack.get(
          `/v1/data/${oldResource}/${oldAId}`,
          stack.ada(`${project}-retired-old-a`),
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await stack.get(
          `/v1/data/${nextResource}/${nextAId}`,
          stack.ada(`${project}-retained-next-a`),
        )
      ).status,
    ).toBe(200);
    expect(
      (
        await stack.get(
          `/v1/data/${oldResource}/${oldBId}`,
          stack.bev(`${project}-old-b-still-v2`),
        )
      ).status,
    ).toBe(200);
    const retiredB = await applyModule(
      config,
      request(tenantB, v3Path, digests.v3, 2),
      approved(digests.v3),
    );
    expect(retiredB).toMatchObject({
      status: "installed",
      moduleVersion: "3.0.0",
      revision: 3,
    });
    expect(
      (
        await stack.get(
          `/v1/data/${oldResource}/${oldBId}`,
          stack.bev(`${project}-retired-old-b`),
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await stack.get(
          `/v1/data/${nextResource}/${nextBId}`,
          stack.bev(`${project}-retained-next-b`),
        )
      ).status,
    ).toBe(200);
    await expect(
      applyModule(
        config,
        request(tenantA, v2Path, digests.v2, 3),
        approved(digests.v2),
      ),
    ).rejects.toMatchObject({
      code: "validation_failed",
      detail: "unsupported upgrade base",
    });
    const final = await stack.ownerQuery(
      "SELECT tenant_id::text AS tenant_id,version,revision FROM core.tenant_modules WHERE module_key=$1 AND tenant_id IN ($2,$3) ORDER BY tenant_id",
      [moduleKey, tenantA, tenantB],
    );
    expect(final.rows).toEqual(
      expect.arrayContaining([
        { tenant_id: tenantA, version: "3.0.0", revision: "3" },
        { tenant_id: tenantB, version: "3.0.0", revision: "3" },
      ]),
    );
    console.log(
      "d08-proof",
      JSON.stringify({
        project,
        schemaHead,
        digests,
        oldAId,
        oldBId,
        nextAId,
        nextBId,
      }),
    );
  } finally {
    try {
      await stack?.stop();
    } finally {
      await rm(scratch, { recursive: true, force: true });
    }
  }
}, 300000);
