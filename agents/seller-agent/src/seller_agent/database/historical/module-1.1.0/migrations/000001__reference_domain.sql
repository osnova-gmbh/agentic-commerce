-- Trusted first-party module; deployment renders the protected tenant schema.
CREATE TABLE {{tenantSchema}}.seller_agent_requests (
    tenant_id uuid NOT NULL REFERENCES core.tenants(tenant_id),
    object_id uuid NOT NULL,
    request_id text NOT NULL CHECK (length(request_id) BETWEEN 1 AND 128),
    description text NOT NULL CHECK (length(description) BETWEEN 1 AND 2000),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    PRIMARY KEY (tenant_id, object_id),
    UNIQUE (tenant_id, request_id),
    FOREIGN KEY (tenant_id, object_id) REFERENCES core.objects(tenant_id, object_id)
);
ALTER TABLE {{tenantSchema}}.seller_agent_requests OWNER TO agentdb_owner;
REVOKE ALL ON {{tenantSchema}}.seller_agent_requests FROM PUBLIC;
ALTER TABLE {{tenantSchema}}.seller_agent_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE {{tenantSchema}}.seller_agent_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY seller_agent_owner ON {{tenantSchema}}.seller_agent_requests
    TO agentdb_owner USING (true) WITH CHECK (true);

CREATE FUNCTION {{tenantSchema}}.seller_agent_get(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE result jsonb;
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.seller-agent',
        'seller_agent.read', ARRAY['tenant_client', 'fenced_worker']);
    SELECT jsonb_build_object('objectId', object_id, 'requestId', request_id,
        'description', description, 'status', status, 'revision', revision)
        INTO result FROM {{tenantSchema}}.seller_agent_requests
        WHERE tenant_id = (ctx->>'tenantId')::uuid
          AND object_id = (input->>'objectId')::uuid;
    IF result IS NULL THEN
        RAISE EXCEPTION 'Reference request not found' USING ERRCODE = 'P0002';
    END IF;
    RETURN result;
END $$;
ALTER FUNCTION {{tenantSchema}}.seller_agent_get(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.seller_agent_get(jsonb, jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.seller_agent_list(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE result jsonb; page_limit integer := (input->>'limit')::integer;
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.seller-agent',
        'seller_agent.read', ARRAY['tenant_client', 'fenced_worker']);
    IF page_limit IS NULL OR page_limit NOT BETWEEN 1 AND 100 THEN
        RAISE EXCEPTION 'Invalid page limit' USING ERRCODE = '22023';
    END IF;
    IF input ? 'filters' OR input ? 'sort' THEN
        RAISE EXCEPTION 'This reference export does not support filters or sorting'
            USING ERRCODE = '22023';
    END IF;
    IF input ? 'select' AND (jsonb_typeof(input->'select') <> 'array'
        OR jsonb_array_length(input->'select') NOT BETWEEN 1 AND 6
        OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(input->'select') field
            WHERE field NOT IN ('objectId', 'requestId', 'description', 'status', 'revision'))) THEN
        RAISE EXCEPTION 'Invalid field selection' USING ERRCODE = '22023';
    END IF;
    SELECT jsonb_strip_nulls(jsonb_build_object('items', COALESCE(jsonb_agg(row ORDER BY object_id), '[]'::jsonb),
        'after', CASE WHEN count(*) = page_limit THEN max(object_id::text) ELSE NULL END)
        )
        INTO result FROM (
            SELECT object_id, CASE WHEN input ? 'select' THEN
                (SELECT jsonb_object_agg(key, value) FROM jsonb_each(full_row)
                    WHERE key = 'objectId' OR input->'select' ? key)
                ELSE full_row END AS row
            FROM (
                SELECT object_id, jsonb_build_object('objectId', object_id,
                    'requestId', request_id, 'description', description,
                    'status', status, 'revision', revision) AS full_row
                FROM {{tenantSchema}}.seller_agent_requests
                WHERE tenant_id = (ctx->>'tenantId')::uuid
                  AND (NOT input ? 'after' OR object_id > (input->>'after')::uuid)
                ORDER BY object_id LIMIT page_limit
            ) selected
        ) page;
    RETURN result;
END $$;
ALTER FUNCTION {{tenantSchema}}.seller_agent_list(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.seller_agent_list(jsonb, jsonb) FROM PUBLIC;
