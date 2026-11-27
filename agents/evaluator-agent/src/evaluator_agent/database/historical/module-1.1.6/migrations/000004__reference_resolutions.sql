-- AgentDb authorizes the tenant and fences the worker before executing either export.
CREATE TABLE {{tenantSchema}}.evaluator_agent_resolutions (
    tenant_id uuid NOT NULL REFERENCES core.tenants(tenant_id),
    installation_id uuid NOT NULL,
    case_id text COLLATE "C" NOT NULL CHECK (length(case_id) BETWEEN 1 AND 256),
    resolution_sha256 bytea NOT NULL CHECK (octet_length(resolution_sha256) = 32),
    resolution text COLLATE "C" NOT NULL CHECK (length(resolution) BETWEEN 1 AND 4096),
    PRIMARY KEY (tenant_id, installation_id, case_id, resolution_sha256),
    FOREIGN KEY (tenant_id, installation_id) REFERENCES core.agent_installations
);
ALTER TABLE {{tenantSchema}}.evaluator_agent_resolutions OWNER TO agentdb_owner;
REVOKE ALL ON {{tenantSchema}}.evaluator_agent_resolutions FROM PUBLIC;
ALTER TABLE {{tenantSchema}}.evaluator_agent_resolutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE {{tenantSchema}}.evaluator_agent_resolutions FORCE ROW LEVEL SECURITY;
CREATE POLICY evaluator_agent_res_owner ON {{tenantSchema}}.evaluator_agent_resolutions
    TO agentdb_owner USING (true) WITH CHECK (true);

CREATE TABLE {{tenantSchema}}.evaluator_agent_res_keys (
    tenant_id uuid NOT NULL REFERENCES core.tenants(tenant_id),
    installation_id uuid NOT NULL,
    request_key_sha256 bytea NOT NULL CHECK (octet_length(request_key_sha256) = 32),
    request_key text COLLATE "C" NOT NULL CHECK (length(request_key) BETWEEN 1 AND 4096),
    case_id text COLLATE "C" NOT NULL,
    resolution_sha256 bytea NOT NULL,
    PRIMARY KEY (tenant_id, installation_id, request_key_sha256),
    FOREIGN KEY (tenant_id, installation_id, case_id, resolution_sha256)
        REFERENCES {{tenantSchema}}.evaluator_agent_resolutions
);
ALTER TABLE {{tenantSchema}}.evaluator_agent_res_keys OWNER TO agentdb_owner;
REVOKE ALL ON {{tenantSchema}}.evaluator_agent_res_keys FROM PUBLIC;
ALTER TABLE {{tenantSchema}}.evaluator_agent_res_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE {{tenantSchema}}.evaluator_agent_res_keys FORCE ROW LEVEL SECURITY;
CREATE POLICY evaluator_agent_res_keys_owner ON {{tenantSchema}}.evaluator_agent_res_keys
    TO agentdb_owner USING (true) WITH CHECK (true);

CREATE FUNCTION {{tenantSchema}}.evaluator_agent_res_apply(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    scope_tenant uuid;
    scope_installation uuid;
    requested_case text := input->>'case_id';
    requested_resolution text := input->>'resolution';
    requested_key text := input->>'request_key';
    resolution_digest bytea := sha256(convert_to(requested_resolution, 'UTF8'));
    key_digest bytea := sha256(convert_to(requested_key, 'UTF8'));
    inserted boolean;
    stored_resolution text;
    stored_key record;
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.evaluator-agent',
        'evaluator_agent.write', ARRAY['fenced_worker']);
    scope_tenant := (ctx->>'tenantId')::uuid;
    scope_installation := (ctx->>'installationId')::uuid;
    INSERT INTO {{tenantSchema}}.evaluator_agent_resolutions
        (tenant_id, installation_id, case_id, resolution_sha256, resolution)
        VALUES (scope_tenant, scope_installation, requested_case, resolution_digest, requested_resolution)
        ON CONFLICT (tenant_id, installation_id, case_id, resolution_sha256) DO NOTHING
        RETURNING true INTO inserted;
    SELECT resolution INTO STRICT stored_resolution
        FROM {{tenantSchema}}.evaluator_agent_resolutions
        WHERE tenant_id = scope_tenant AND installation_id = scope_installation
          AND case_id = requested_case
          AND resolution_sha256 = resolution_digest;
    IF convert_to(stored_resolution, 'UTF8') IS DISTINCT FROM convert_to(requested_resolution, 'UTF8') THEN
        RAISE EXCEPTION 'Resolution digest is bound to different text' USING ERRCODE = '23505';
    END IF;
    INSERT INTO {{tenantSchema}}.evaluator_agent_res_keys
        (tenant_id, installation_id, request_key_sha256, request_key, case_id, resolution_sha256)
        VALUES (scope_tenant, scope_installation, key_digest, requested_key, requested_case, resolution_digest)
        ON CONFLICT (tenant_id, installation_id, request_key_sha256) DO NOTHING;
    SELECT request_key, case_id, resolution_sha256 INTO STRICT stored_key
        FROM {{tenantSchema}}.evaluator_agent_res_keys
        WHERE tenant_id = scope_tenant AND installation_id = scope_installation
          AND request_key_sha256 = key_digest;
    IF convert_to(stored_key.request_key, 'UTF8') IS DISTINCT FROM convert_to(requested_key, 'UTF8')
       OR convert_to(stored_key.case_id, 'UTF8') IS DISTINCT FROM convert_to(requested_case, 'UTF8')
       OR stored_key.resolution_sha256 IS DISTINCT FROM resolution_digest THEN
        RAISE EXCEPTION 'Idempotency key is bound to another resolution' USING ERRCODE = '23505';
    END IF;
    RETURN jsonb_build_object('applied', true, 'already_applied', NOT coalesce(inserted, false));
END $$;
ALTER FUNCTION {{tenantSchema}}.evaluator_agent_res_apply(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.evaluator_agent_res_apply(jsonb, jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.evaluator_agent_res_list(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE result jsonb;
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.evaluator-agent',
        'evaluator_agent.read', ARRAY['fenced_worker']);
    SELECT coalesce(jsonb_agg(resolution ORDER BY resolution), '[]'::jsonb) INTO result
        FROM (SELECT resolution FROM {{tenantSchema}}.evaluator_agent_resolutions
            WHERE tenant_id = (ctx->>'tenantId')::uuid
              AND installation_id = (ctx->>'installationId')::uuid AND case_id = input->>'case_id'
            ORDER BY resolution LIMIT 100) AS bounded;
    RETURN jsonb_build_object('case_id', input->>'case_id', 'resolutions', result);
END $$;
ALTER FUNCTION {{tenantSchema}}.evaluator_agent_res_list(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.evaluator_agent_res_list(jsonb, jsonb) FROM PUBLIC;
