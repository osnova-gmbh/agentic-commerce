CREATE FUNCTION {{tenantSchema}}.ac_catalog_company_read(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'company.read')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_company_read(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_company_read(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_companies_list(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'companies.list')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_companies_list(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_companies_list(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_sellers_list(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'sellers.list')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_sellers_list(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_sellers_list(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_catalog_read(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'catalog.read')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_catalog_read(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_catalog_read(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_evaluators_list(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'evaluators.list')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_evaluators_list(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_evaluators_list(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_company_upsert(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'company.upsert')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_company_upsert(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_company_upsert(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_evaluator_upsert(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'evaluator.upsert')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_evaluator_upsert(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_evaluator_upsert(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_catalog_publish(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-catalog', 'ac_catalog.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_catalog_dispatch(ctx, (input->>'payload')::jsonb, 'catalog.publish')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_catalog_catalog_publish(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_catalog_publish(jsonb,jsonb) FROM PUBLIC;
