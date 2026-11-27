CREATE FUNCTION {{tenantSchema}}.ac_msg_identity_resolve(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'identity.resolve')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_identity_resolve(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_identity_resolve(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_conversation_read(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.read', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'conversation.read')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_conversation_read(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_conversation_read(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_identity_register(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'identity.register')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_identity_register(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_identity_register(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_type_register(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'type.register')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_type_register(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_type_register(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_message_send(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'message.send')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_message_send(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_message_send(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_message_claim(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'message.claim')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_message_claim(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_message_claim(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_message_ack(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'message.ack')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_message_ack(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_message_ack(jsonb,jsonb) FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_message_release(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, 'cogit-messaging', 'ac_msg.write', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{tenantSchema}}.ac_msg_dispatch(ctx, (input->>'payload')::jsonb, 'message.release')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{tenantSchema}}.ac_msg_message_release(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_message_release(jsonb,jsonb) FROM PUBLIC;
