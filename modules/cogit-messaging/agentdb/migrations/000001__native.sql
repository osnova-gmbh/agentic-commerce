
CREATE TABLE {{tenantSchema}}.ac_msg_records (
  tenant_id uuid NOT NULL, kind text NOT NULL, id text NOT NULL,
  doc jsonb NOT NULL CHECK (jsonb_typeof(doc) = 'object'),
  ordinal bigint GENERATED ALWAYS AS IDENTITY,
  PRIMARY KEY (tenant_id, kind, id)
);
ALTER TABLE {{tenantSchema}}.ac_msg_records OWNER TO agentdb_owner;
REVOKE ALL ON {{tenantSchema}}.ac_msg_records FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_msg_error(code text) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN RAISE EXCEPTION USING ERRCODE = 'P0200', MESSAGE = code; END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_text(v jsonb, k text, optional boolean DEFAULT false)
RETURNS text LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF optional AND (NOT v ? k OR v->k = 'null'::jsonb) THEN RETURN NULL; END IF;
  IF jsonb_typeof(v->k) IS DISTINCT FROM 'string' OR length(v->>k)=0 THEN
    PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument');
  END IF;
  RETURN v->>k;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_int(v jsonb, k text, fallback bigint DEFAULT NULL, minimum bigint DEFAULT 0)
RETURNS bigint LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE n bigint;
BEGIN
  IF NOT v ? k OR v->k='null'::jsonb THEN n:=fallback;
  ELSIF jsonb_typeof(v->k)='number' AND (v->>k) ~ '^-?[0-9]+$' THEN n:=(v->>k)::bigint;
  ELSE PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
  IF n IS NULL OR n<minimum THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
  RETURN n;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_clean(v jsonb, rules jsonb, partial boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE result jsonb:='{}'; k text; r jsonb; item jsonb; typ text; valid boolean;
BEGIN
  IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(v) x WHERE NOT rules ? x) THEN
    PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument');
  END IF;
  FOR k,r IN SELECT key,value FROM jsonb_each(rules) LOOP
    IF partial AND NOT v ? k THEN CONTINUE; END IF;
    item:=v->k;
    IF item IS NULL OR item='null'::jsonb THEN
      IF COALESCE((r->>'required')::boolean,false) THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
      IF partial AND r->>'nullable' IS DISTINCT FROM 'true' THEN CONTINUE; END IF;
      result:=result||jsonb_build_object(k,CASE WHEN partial THEN item ELSE r->'default' END);
      CONTINUE;
    END IF;
    typ:=r->>'type'; valid:=true;
    IF typ='text' THEN valid:=jsonb_typeof(item)='string' AND (NOT COALESCE((r->>'required')::boolean,false) OR length(item#>>'{}')>0);
    ELSIF typ IN ('int','signed','positive') THEN
      valid:=jsonb_typeof(item)='number' AND (item#>>'{}') ~ '^-?[0-9]+$';
      IF valid AND typ<>'signed' THEN valid:=(item#>>'{}')::numeric >= CASE typ WHEN 'positive' THEN 1 ELSE 0 END; END IF;
    ELSIF typ='bool' THEN valid:=jsonb_typeof(item)='boolean';
    ELSIF typ='object' THEN valid:=jsonb_typeof(item)='object';
    ELSIF typ='texts' THEN
      valid:=jsonb_typeof(item)='array';
      IF valid THEN valid:=NOT EXISTS(SELECT 1 FROM jsonb_array_elements(item) x WHERE jsonb_typeof(x)<>'string' OR x#>>'{}'=''); END IF;
    END IF;
    IF r ? 'enum' THEN valid:=valid AND r->'enum' @> jsonb_build_array(item); END IF;
    IF NOT valid THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
    result:=result||jsonb_build_object(k,item);
  END LOOP;
  RETURN result;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_get(t uuid, k text, ident text) RETURNS jsonb
LANGUAGE sql SET search_path = pg_catalog AS $$
  SELECT doc FROM {{tenantSchema}}.ac_msg_records WHERE tenant_id=t AND kind=k AND id=ident;
$$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_put(t uuid,k text,ident text,value jsonb) RETURNS void
LANGUAGE sql SET search_path = pg_catalog AS $$
  INSERT INTO {{tenantSchema}}.ac_msg_records(tenant_id,kind,id,doc) VALUES(t,k,ident,value)
  ON CONFLICT(tenant_id,kind,id) DO UPDATE SET doc=excluded.doc;
$$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_operator(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ctx->>'callerKind' IS DISTINCT FROM 'tenant_client'
     OR NULLIF(ctx#>>'{settings,operator_principal_id}','') IS NULL
     OR ctx->>'principalId' IS DISTINCT FROM ctx#>>'{settings,operator_principal_id}' THEN
    PERFORM {{tenantSchema}}.ac_msg_error('forbidden');
  END IF;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_escrow(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ctx->>'callerKind' IS DISTINCT FROM 'fenced_worker'
     OR ctx->>'installationId' IS DISTINCT FROM ctx#>>'{settings,escrow_installation_id}' THEN
    PERFORM {{tenantSchema}}.ac_msg_error('forbidden');
  END IF;
END $$;

CREATE INDEX ac_msg_inbox ON {{tenantSchema}}.ac_msg_records(tenant_id,(doc->>'recipient_did'),ordinal) WHERE kind='message';
CREATE INDEX ac_msg_conversation ON {{tenantSchema}}.ac_msg_records(tenant_id,(doc->>'conversation_id'),ordinal) WHERE kind='message';

CREATE FUNCTION {{tenantSchema}}.ac_msg_no_float(v jsonb) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE item jsonb;
BEGIN
  IF jsonb_typeof(v)='number' THEN RETURN (v#>>'{}') ~ '^-?[0-9]+$'; END IF;
  IF jsonb_typeof(v)='array' THEN
    FOR item IN SELECT value FROM jsonb_array_elements(v) LOOP IF NOT {{tenantSchema}}.ac_msg_no_float(item) THEN RETURN false; END IF; END LOOP;
  ELSIF jsonb_typeof(v)='object' THEN
    FOR item IN SELECT value FROM jsonb_each(v) LOOP IF NOT {{tenantSchema}}.ac_msg_no_float(item) THEN RETURN false; END IF; END LOOP;
  END IF;
  RETURN true;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_schema(s jsonb,depth integer DEFAULT 0) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE k text; item jsonb; typ jsonb;
BEGIN
  IF depth>12 OR jsonb_typeof(s) IS DISTINCT FROM 'object' OR NOT {{tenantSchema}}.ac_msg_no_float(s)
    OR EXISTS(SELECT 1 FROM jsonb_object_keys(s) x WHERE x NOT IN ('type','properties','required','additionalProperties','items','enum','minLength','maxLength','minimum','maximum','minItems','maxItems','description')) THEN RETURN false; END IF;
  typ:=s->'type';
  IF typ IS NOT NULL THEN
    IF jsonb_typeof(typ)='string' THEN
      IF typ#>>'{}' NOT IN ('object','array','string','integer','number','boolean','null') THEN RETURN false; END IF;
    ELSIF jsonb_typeof(typ)='array' THEN
      IF jsonb_array_length(typ)<>2 OR NOT typ ? 'null' OR typ->0=typ->1 OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(typ) x WHERE x NOT IN ('object','array','string','integer','number','boolean','null')) THEN RETURN false; END IF;
    ELSE RETURN false; END IF;
  END IF;
  IF s ? 'description' AND jsonb_typeof(s->'description')<>'string' THEN RETURN false; END IF;
  IF s ? 'additionalProperties' AND s->'additionalProperties'<>'false'::jsonb THEN RETURN false; END IF;
  IF s ? 'required' THEN
    IF jsonb_typeof(s->'required')<>'array' THEN RETURN false; END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(s->'required') x WHERE jsonb_typeof(x)<>'string') THEN RETURN false; END IF;
  END IF;
  IF s ? 'enum' THEN
    IF jsonb_typeof(s->'enum')<>'array' THEN RETURN false; END IF;
    IF jsonb_array_length(s->'enum')=0 OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'enum') x WHERE jsonb_typeof(x) NOT IN ('string','number','boolean','null')) THEN RETURN false; END IF;
  END IF;
  FOREACH k IN ARRAY ARRAY['minLength','maxLength','minItems','maxItems','minimum','maximum'] LOOP
    IF s ? k THEN
      IF jsonb_typeof(s->k)<>'number' OR s->>k !~ '^-?[0-9]+$' THEN RETURN false; END IF;
      IF k NOT IN ('minimum','maximum') AND (s->>k)::numeric<0 THEN RETURN false; END IF;
    END IF;
  END LOOP;
  IF s ? 'properties' THEN
    IF jsonb_typeof(s->'properties')<>'object' THEN RETURN false; END IF;
    FOR item IN SELECT value FROM jsonb_each(s->'properties') LOOP IF NOT {{tenantSchema}}.ac_msg_schema(item,depth+1) THEN RETURN false; END IF; END LOOP;
  END IF;
  IF s ? 'items' AND NOT {{tenantSchema}}.ac_msg_schema(s->'items',depth+1) THEN RETURN false; END IF;
  RETURN true;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_matches(s jsonb,v jsonb,depth integer DEFAULT 0) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE k text; item jsonb; typ text:=jsonb_typeof(v); expected jsonb:=s->'type';
BEGIN
  IF depth>12 OR v IS NULL THEN RETURN false; END IF;
  IF expected IS NOT NULL THEN
    IF typ='number' AND (expected='"integer"'::jsonb OR expected ? 'integer') AND v#>>'{}' ~ '^-?[0-9]+$' THEN NULL;
    ELSIF NOT (expected=to_jsonb(typ) OR jsonb_typeof(expected)='array' AND expected ? typ) THEN RETURN false; END IF;
  END IF;
  IF s ? 'enum' AND NOT s->'enum' @> jsonb_build_array(v) THEN RETURN false; END IF;
  IF typ='object' THEN
    IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(COALESCE(s->'required','[]')) x WHERE NOT v ? x) THEN RETURN false; END IF;
    FOR k,item IN SELECT key,value FROM jsonb_each(v) LOOP
      IF s->'properties' ? k THEN
        IF NOT {{tenantSchema}}.ac_msg_matches(s->'properties'->k,item,depth+1) THEN RETURN false; END IF;
      ELSIF s->'additionalProperties'='false'::jsonb THEN RETURN false; END IF;
    END LOOP;
  ELSIF typ='array' THEN
    IF s ? 'minItems' AND jsonb_array_length(v)<(s->>'minItems')::numeric OR s ? 'maxItems' AND jsonb_array_length(v)>(s->>'maxItems')::numeric THEN RETURN false; END IF;
    IF s ? 'items' THEN FOR item IN SELECT value FROM jsonb_array_elements(v) LOOP IF NOT {{tenantSchema}}.ac_msg_matches(s->'items',item,depth+1) THEN RETURN false; END IF; END LOOP; END IF;
  ELSIF typ='string' THEN
    IF s ? 'minLength' AND length(v#>>'{}')<(s->>'minLength')::numeric OR s ? 'maxLength' AND length(v#>>'{}')>(s->>'maxLength')::numeric THEN RETURN false; END IF;
  ELSIF typ='number' THEN
    IF s ? 'minimum' AND (v#>>'{}')::numeric<(s->>'minimum')::numeric OR s ? 'maximum' AND (v#>>'{}')::numeric>(s->>'maximum')::numeric THEN RETURN false; END IF;
  END IF;
  RETURN true;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_msg_dispatch(ctx jsonb,a jsonb,op text) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; installation text:=ctx->>'installationId'; k text; ident text; row jsonb; item jsonb; env jsonb;
  result jsonb; schema_doc jsonb; n bigint; version bigint; delay_s bigint; rec record;
  moment timestamptz:=clock_timestamp(); stamp text:=to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'); stale text;
  maximum bigint:=COALESCE((ctx#>>'{settings,max_delivery_attempts}')::bigint,5);
BEGIN
  IF jsonb_typeof(a) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
  IF op='identity.register' THEN
    PERFORM {{tenantSchema}}.ac_msg_operator(ctx);
    ident:={{tenantSchema}}.ac_msg_text(a,'did');
    PERFORM {{tenantSchema}}.ac_msg_text(a,'installation_id'); PERFORM {{tenantSchema}}.ac_msg_text(a,'org_id');
    IF a->>'role' IS NULL OR a->>'role' NOT IN ('buyer','seller','evaluator','escrow') THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
    row:={{tenantSchema}}.ac_msg_get(t,'identity',ident);
    PERFORM {{tenantSchema}}.ac_msg_put(t,'identity',ident,jsonb_build_object('did',ident,'installation_id',a->'installation_id','org_id',a->'org_id','role',a->'role','active',true,'registered_at',COALESCE(row->>'registered_at',stamp)));
    RETURN jsonb_build_object('did',ident);
  ELSIF op='identity.resolve' THEN
    IF a->>'did' IS NOT NULL THEN row:={{tenantSchema}}.ac_msg_get(t,'identity',a->>'did');
    ELSIF a->>'role' IS NOT NULL THEN
      SELECT doc INTO row FROM {{tenantSchema}}.ac_msg_records WHERE tenant_id=t AND kind='identity' AND doc->'active'='true'::jsonb AND doc->>'role'=a->>'role' AND (a->>'org_id' IS NULL OR doc->>'org_id'=a->>'org_id') ORDER BY doc->>'registered_at',id LIMIT 1;
    ELSE PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
    RETURN jsonb_build_object('identity',CASE WHEN row->'active'='true'::jsonb THEN row ELSE NULL END);
  ELSIF op='type.register' THEN
    PERFORM {{tenantSchema}}.ac_msg_escrow(ctx);
    ident:={{tenantSchema}}.ac_msg_text(a,'type_key'); version:={{tenantSchema}}.ac_msg_int(a,'type_version',NULL,1);
    schema_doc:=a->'json_schema';
    IF NOT {{tenantSchema}}.ac_msg_schema(schema_doc) THEN PERFORM {{tenantSchema}}.ac_msg_error('unsupported_schema'); END IF;
    k:=jsonb_build_array(ident,version)::text;
    PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':type:'||k,0));
    row:={{tenantSchema}}.ac_msg_get(t,'type',k);
    IF row IS NULL THEN
      PERFORM {{tenantSchema}}.ac_msg_put(t,'type',k,jsonb_build_object('type_key',ident,'type_version',version,'json_schema',schema_doc,'registered_by',installation,'registered_at',stamp));
      RETURN '{"status":"created"}';
    ELSIF row->'json_schema'=schema_doc THEN RETURN '{"status":"unchanged"}';
    ELSE PERFORM {{tenantSchema}}.ac_msg_error('type_conflict'); END IF;
  ELSIF op='message.send' THEN
    env:=a->'envelope';
    IF jsonb_typeof(env) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_envelope'); END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(env))<>11 OR NOT env ?& ARRAY['envelope_version','message_id','type_key','type_version','sender_did','recipient_did','conversation_id','causation_id','created_at','body','signature']
      OR env->'envelope_version'<>'1'::jsonb OR NOT {{tenantSchema}}.ac_msg_no_float(env) THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_envelope'); END IF;
    FOREACH k IN ARRAY ARRAY['message_id','type_key','sender_did','recipient_did','conversation_id','signature'] LOOP
      IF jsonb_typeof(env->k) IS DISTINCT FROM 'string' OR length(env->>k) NOT BETWEEN 1 AND 512 THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_envelope'); END IF;
    END LOOP;
    IF jsonb_typeof(env->'type_version') IS DISTINCT FROM 'number' OR env->>'type_version' !~ '^[1-9][0-9]*$'
      OR jsonb_typeof(env->'body') IS DISTINCT FROM 'object' OR env->>'created_at' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'
      OR (env->'causation_id'<>'null'::jsonb AND (jsonb_typeof(env->'causation_id')<>'string' OR env->>'causation_id'='')) THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_envelope'); END IF;
    row:={{tenantSchema}}.ac_msg_get(t,'identity',env->>'sender_did');
    IF ctx->>'callerKind'<>'fenced_worker' OR row->>'installation_id' IS DISTINCT FROM installation OR row->'active' IS DISTINCT FROM 'true'::jsonb THEN PERFORM {{tenantSchema}}.ac_msg_error('not_your_did'); END IF;
    ident:=env->>'message_id';
    PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':message:'||ident,0));
    IF {{tenantSchema}}.ac_msg_get(t,'message',ident) IS NOT NULL THEN RETURN jsonb_build_object('message_id',ident,'status','duplicate'); END IF;
    row:={{tenantSchema}}.ac_msg_get(t,'identity',env->>'recipient_did');
    IF row->'active' IS DISTINCT FROM 'true'::jsonb THEN PERFORM {{tenantSchema}}.ac_msg_error('unknown_recipient'); END IF;
    row:={{tenantSchema}}.ac_msg_get(t,'type',jsonb_build_array(env->>'type_key',env->'type_version')::text);
    IF row IS NULL THEN PERFORM {{tenantSchema}}.ac_msg_error('unknown_type'); END IF;
    IF NOT {{tenantSchema}}.ac_msg_matches(row->'json_schema',env->'body') THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_body'); END IF;
    INSERT INTO {{tenantSchema}}.ac_msg_records(tenant_id,kind,id,doc) VALUES(t,'message',ident,
      jsonb_build_object('message_id',ident,'conversation_id',env->'conversation_id','causation_id',env->'causation_id','type_key',env->'type_key','type_version',env->'type_version','sender_did',env->'sender_did','recipient_did',env->'recipient_did','envelope',env,'status','queued','attempts',0,'available_at',stamp,'created_at',stamp,'claimed_at',NULL,'admission_key',NULL,'run_id',NULL,'reason',NULL,'acked_at',NULL));
    RETURN jsonb_build_object('message_id',ident,'status','queued');
  ELSIF op='message.claim' THEN
    IF ctx->>'callerKind'<>'fenced_worker' OR installation IS NULL THEN PERFORM {{tenantSchema}}.ac_msg_error('forbidden'); END IF;
    n:=least({{tenantSchema}}.ac_msg_int(a,'limit',10,1),100); result:='[]';
    stale:=to_char((moment-make_interval(secs=>COALESCE((ctx#>>'{settings,redeliver_after_s}')::integer,30))) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"');
    FOR rec IN SELECT r.id,r.doc FROM {{tenantSchema}}.ac_msg_records r
      WHERE r.tenant_id=t AND r.kind='message' AND EXISTS(SELECT 1 FROM {{tenantSchema}}.ac_msg_records i WHERE i.tenant_id=t AND i.kind='identity' AND i.id=r.doc->>'recipient_did' AND i.doc->>'installation_id'=installation AND i.doc->'active'='true'::jsonb)
      AND (r.doc->>'status'='queued' AND r.doc->>'available_at'<=stamp OR r.doc->>'status'='claimed' AND r.doc->>'claimed_at'<=stale)
      ORDER BY r.ordinal FOR UPDATE OF r SKIP LOCKED LOOP
      IF (rec.doc->>'attempts')::bigint>=maximum THEN
        PERFORM {{tenantSchema}}.ac_msg_put(t,'message',rec.id,rec.doc||jsonb_build_object('status','dead','reason','max_delivery_attempts','acked_at',stamp));
        CONTINUE;
      END IF;
      IF jsonb_array_length(result)>=n THEN EXIT; END IF;
      row:=rec.doc||jsonb_build_object('status','claimed','claimed_at',stamp,'attempts',(rec.doc->>'attempts')::bigint+1,'admission_key','msg:'||rec.id);
      PERFORM {{tenantSchema}}.ac_msg_put(t,'message',rec.id,row);
      result:=result||jsonb_build_array(jsonb_build_object('message_id',rec.id,'envelope',row->'envelope','attempts',row->'attempts'));
    END LOOP;
    RETURN jsonb_build_object('messages',result);
  ELSIF op IN ('message.ack','message.release') THEN
    ident:={{tenantSchema}}.ac_msg_text(a,'message_id');
    SELECT doc INTO row FROM {{tenantSchema}}.ac_msg_records WHERE tenant_id=t AND kind='message' AND id=ident FOR UPDATE;
    IF row IS NULL THEN PERFORM {{tenantSchema}}.ac_msg_error('unknown_message'); END IF;
    item:={{tenantSchema}}.ac_msg_get(t,'identity',row->>'recipient_did');
    IF ctx->>'callerKind'<>'fenced_worker' OR item->>'installation_id' IS DISTINCT FROM installation OR item->'active' IS DISTINCT FROM 'true'::jsonb THEN PERFORM {{tenantSchema}}.ac_msg_error('not_your_message'); END IF;
    IF op='message.ack' THEN
      IF a->>'outcome' IS NULL OR a->>'outcome' NOT IN ('processed','rejected') THEN PERFORM {{tenantSchema}}.ac_msg_error('invalid_argument'); END IF;
      IF row->>'status' NOT IN ('processed','rejected','dead') THEN
        row:=row||jsonb_build_object('status',a->'outcome','reason',a->'reason','run_id',COALESCE(NULLIF(a->'run_id','null'),row->'run_id'),'acked_at',stamp);
      END IF;
    ELSE
      delay_s:={{tenantSchema}}.ac_msg_int(a,'delay_s',0);
      IF row->>'status'='claimed' THEN
        IF (row->>'attempts')::bigint>=maximum THEN row:=row||jsonb_build_object('status','dead','reason','max_delivery_attempts','acked_at',stamp);
        ELSE row:=row||jsonb_build_object('status','queued','available_at',to_char((moment+make_interval(secs=>delay_s)) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"')); END IF;
      END IF;
    END IF;
    PERFORM {{tenantSchema}}.ac_msg_put(t,'message',ident,row); RETURN '{}';
  ELSIF op='conversation.read' THEN
    ident:={{tenantSchema}}.ac_msg_text(a,'conversation_id');
    SELECT COALESCE(jsonb_agg(doc-'conversation_id'-'claimed_at'-'available_at'-'admission_key' ORDER BY ordinal),'[]') INTO result
      FROM {{tenantSchema}}.ac_msg_records WHERE tenant_id=t AND kind='message' AND doc->>'conversation_id'=ident;
    RETURN jsonb_build_object('messages',result);
  END IF;
  PERFORM {{tenantSchema}}.ac_msg_error('unknown_export');
END $$;

ALTER FUNCTION {{tenantSchema}}.ac_msg_error(text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_error(text) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_text(jsonb,text,boolean) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_text(jsonb,text,boolean) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_int(jsonb,text,bigint,bigint) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_int(jsonb,text,bigint,bigint) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_clean(jsonb,jsonb,boolean) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_clean(jsonb,jsonb,boolean) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_get(uuid,text,text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_get(uuid,text,text) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_put(uuid,text,text,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_put(uuid,text,text,jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_operator(jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_operator(jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_escrow(jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_escrow(jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_no_float(jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_no_float(jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_schema(jsonb,integer) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_schema(jsonb,integer) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_matches(jsonb,jsonb,integer) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_matches(jsonb,jsonb,integer) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_msg_dispatch(jsonb,jsonb,text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_msg_dispatch(jsonb,jsonb,text) FROM PUBLIC;
