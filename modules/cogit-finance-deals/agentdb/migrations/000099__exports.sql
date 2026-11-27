CREATE FUNCTION {{tenantSchema}}.ac_deals_outbox_pending(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-deals', 'ac_deals.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_deals_dispatch(ctx, (input->>'payload')::jsonb, 'outbox.pending')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_deals_outbox_pending(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_outbox_pending(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_deals_deal_read(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-deals', 'ac_deals.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_deals_dispatch(ctx, (input->>'payload')::jsonb, 'deal.read')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_deals_deal_read(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_deal_read(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_deals_deal_list(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-deals', 'ac_deals.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_deals_dispatch(ctx, (input->>'payload')::jsonb, 'deal.list')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_deals_deal_list(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_deal_list(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_deals_ledger_balances(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-deals', 'ac_deals.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_deals_dispatch(ctx, (input->>'payload')::jsonb, 'ledger.balances')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_deals_ledger_balances(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_ledger_balances(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_deals_deal_commit(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-deals', 'ac_deals.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_deals_dispatch(ctx, (input->>'payload')::jsonb, 'deal.commit')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_deals_deal_commit(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_deal_commit(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_deals_outbox_mark_sent(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-deals', 'ac_deals.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_deals_dispatch(ctx, (input->>'payload')::jsonb, 'outbox.mark_sent')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_deals_outbox_mark_sent(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_outbox_mark_sent(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_deals_intent_update(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-finance-deals', 'ac_deals.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_deals_dispatch(ctx, (input->>'payload')::jsonb, 'intent.update')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_deals_intent_update(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_intent_update(jsonb,jsonb) FROM PUBLIC;
