CREATE FUNCTION {{tenantSchema}}.seller_agent_create(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE new_id uuid; result jsonb;
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.seller-agent',
        'seller_agent.write', ARRAY['tenant_client', 'fenced_worker']);
    IF input->>'requestId' IS NULL OR length(input->>'requestId') NOT BETWEEN 1 AND 128
        OR input->>'description' IS NULL
        OR length(input->>'description') NOT BETWEEN 1 AND 2000 THEN
        RAISE EXCEPTION 'Invalid reference request' USING ERRCODE = '22023';
    END IF;
    new_id := core.module_object_create(ctx, 'seller_agent_request',
        1, input->>'requestId');
    INSERT INTO {{tenantSchema}}.seller_agent_requests(tenant_id, object_id, request_id, description)
        VALUES ((ctx->>'tenantId')::uuid, new_id, input->>'requestId', input->>'description')
        ON CONFLICT (tenant_id, request_id) DO NOTHING;
    SELECT jsonb_build_object('objectId', object_id, 'requestId', request_id,
        'description', description, 'status', status, 'revision', revision)
        INTO result FROM {{tenantSchema}}.seller_agent_requests
        WHERE tenant_id = (ctx->>'tenantId')::uuid AND object_id = new_id;
    IF result->>'description' IS DISTINCT FROM input->>'description' THEN
        RAISE EXCEPTION 'Request identity already has different content' USING ERRCODE = '23505';
    END IF;
    RETURN result;
END $$;
ALTER FUNCTION {{tenantSchema}}.seller_agent_create(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.seller_agent_create(jsonb, jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.seller_agent_put(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.seller-agent',
        'seller_agent.write', ARRAY['fenced_worker']);
    RETURN {{tenantSchema}}.seller_agent_create(ctx, input);
END $$;
ALTER FUNCTION {{tenantSchema}}.seller_agent_put(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.seller_agent_put(jsonb, jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.seller_agent_close(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE result jsonb;
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.seller-agent',
        'seller_agent.write', ARRAY['tenant_client']);
    UPDATE {{tenantSchema}}.seller_agent_requests SET status = 'closed', revision = revision + 1
        WHERE tenant_id = (ctx->>'tenantId')::uuid AND object_id = (input->>'objectId')::uuid
          AND revision = (input->>'expectedRevision')::integer
        RETURNING jsonb_build_object('objectId', object_id, 'requestId', request_id,
            'description', description, 'status', status, 'revision', revision) INTO result;
    IF result IS NULL THEN
        RAISE EXCEPTION 'Reference request not found or revision conflict' USING ERRCODE = '40001';
    END IF;
    RETURN result;
END $$;
ALTER FUNCTION {{tenantSchema}}.seller_agent_close(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.seller_agent_close(jsonb, jsonb) FROM PUBLIC;
