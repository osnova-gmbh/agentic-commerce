-- The v1 list function remains in the historical migration. The D01 facade
-- projects fields itself and supplies an empty cursor for the first page.
CREATE FUNCTION {{tenantSchema}}.cogit_finance_list_v2(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    result jsonb;
    page_limit integer;
    cursor_id uuid;
BEGIN
    PERFORM core.require_module_context(ctx, 'cogit.cogit-finance',
        'cogit_finance.read', ARRAY['tenant_client', 'fenced_worker']);
    IF jsonb_typeof(input) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'Invalid reference list input' USING ERRCODE = '22023';
    END IF;
    -- The facade can forward empty controls. No filters or sort fields are
    -- registered for this resource, so only their no-op forms are accepted.
    IF (input - 'limit' - 'after' - 'filters' - 'sort') <> '{}'::jsonb
        OR (input ? 'filters' AND input->'filters' <> '{}'::jsonb)
        OR (input ? 'sort' AND input->'sort' <> '{}'::jsonb) THEN
        RAISE EXCEPTION 'This reference export does not support filters or sorting'
            USING ERRCODE = '22023';
    END IF;
    IF input ? 'after' AND jsonb_typeof(input->'after') <> 'string' THEN
        RAISE EXCEPTION 'Invalid page cursor' USING ERRCODE = '22023';
    END IF;
    page_limit := (input->>'limit')::integer;
    IF page_limit IS NULL OR page_limit NOT BETWEEN 1 AND 100 THEN
        RAISE EXCEPTION 'Invalid page limit' USING ERRCODE = '22023';
    END IF;
    IF COALESCE(input->>'after', '') <> '' THEN
        cursor_id := (input->>'after')::uuid;
    END IF;
    SELECT jsonb_strip_nulls(jsonb_build_object(
        'items', COALESCE(jsonb_agg(page.full_row ORDER BY page.object_id), '[]'::jsonb),
        'after', CASE WHEN count(*) = page_limit THEN max(page.object_id::text) ELSE NULL END
    )) INTO result
    FROM (
        SELECT object_id, jsonb_build_object(
            'objectId', object_id,
            'requestId', request_id,
            'description', description,
            'status', status,
            'revision', revision
        ) AS full_row
        FROM {{tenantSchema}}.cogit_finance_requests
        WHERE tenant_id = (ctx->>'tenantId')::uuid
          AND (cursor_id IS NULL OR object_id > cursor_id)
        ORDER BY object_id
        LIMIT page_limit
    ) page;
    RETURN result;
END $$;
ALTER FUNCTION {{tenantSchema}}.cogit_finance_list_v2(jsonb, jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.cogit_finance_list_v2(jsonb, jsonb) FROM PUBLIC;
