
CREATE TABLE {{tenantSchema}}.ac_catalog_records (
  tenant_id uuid NOT NULL, kind text NOT NULL, id text NOT NULL,
  doc jsonb NOT NULL CHECK (jsonb_typeof(doc) = 'object'),
  ordinal bigint GENERATED ALWAYS AS IDENTITY,
  PRIMARY KEY (tenant_id, kind, id)
);
ALTER TABLE {{tenantSchema}}.ac_catalog_records OWNER TO agentdb_owner;
REVOKE ALL ON {{tenantSchema}}.ac_catalog_records FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_error(code text) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN RAISE EXCEPTION USING ERRCODE = 'P0200', MESSAGE = code; END $$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_text(v jsonb, k text, optional boolean DEFAULT false)
RETURNS text LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF optional AND (NOT v ? k OR v->k = 'null'::jsonb) THEN RETURN NULL; END IF;
  IF jsonb_typeof(v->k) IS DISTINCT FROM 'string' OR length(v->>k)=0 THEN
    PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument');
  END IF;
  RETURN v->>k;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_int(v jsonb, k text, fallback bigint DEFAULT NULL, minimum bigint DEFAULT 0)
RETURNS bigint LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE n bigint;
BEGIN
  IF NOT v ? k OR v->k='null'::jsonb THEN n:=fallback;
  ELSIF jsonb_typeof(v->k)='number' AND (v->>k) ~ '^-?[0-9]+$' THEN n:=(v->>k)::bigint;
  ELSE PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
  IF n IS NULL OR n<minimum THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
  RETURN n;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_clean(v jsonb, rules jsonb, partial boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE result jsonb:='{}'; k text; r jsonb; item jsonb; typ text; valid boolean;
BEGIN
  IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(v) x WHERE NOT rules ? x) THEN
    PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument');
  END IF;
  FOR k,r IN SELECT key,value FROM jsonb_each(rules) LOOP
    IF partial AND NOT v ? k THEN CONTINUE; END IF;
    item:=v->k;
    IF item IS NULL OR item='null'::jsonb THEN
      IF COALESCE((r->>'required')::boolean,false) THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
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
    IF NOT valid THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
    result:=result||jsonb_build_object(k,item);
  END LOOP;
  RETURN result;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_get(t uuid, k text, ident text) RETURNS jsonb
LANGUAGE sql SET search_path = pg_catalog AS $$
  SELECT doc FROM {{tenantSchema}}.ac_catalog_records WHERE tenant_id=t AND kind=k AND id=ident;
$$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_put(t uuid,k text,ident text,value jsonb) RETURNS void
LANGUAGE sql SET search_path = pg_catalog AS $$
  INSERT INTO {{tenantSchema}}.ac_catalog_records(tenant_id,kind,id,doc) VALUES(t,k,ident,value)
  ON CONFLICT(tenant_id,kind,id) DO UPDATE SET doc=excluded.doc;
$$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_operator(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ((ctx->>'callerKind'='tenant_client'
      AND NULLIF(ctx#>>'{settings,operator_principal_id}','') IS NOT NULL
      AND ctx->>'principalId'=ctx#>>'{settings,operator_principal_id}')
    OR (ctx->>'callerKind'='fenced_worker' AND ctx->>'installationId'=ctx#>>'{settings,escrow_installation_id}')) IS NOT TRUE THEN
    PERFORM {{tenantSchema}}.ac_catalog_error('forbidden');
  END IF;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_escrow(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ctx->>'callerKind' IS DISTINCT FROM 'fenced_worker'
     OR ctx->>'installationId' IS DISTINCT FROM ctx#>>'{settings,escrow_installation_id}' THEN
    PERFORM {{tenantSchema}}.ac_catalog_error('forbidden');
  END IF;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_catalog_dispatch(ctx jsonb,a jsonb,op text) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; row jsonb; item jsonb; result jsonb; ident text; role_filter text; category text; ids text[]:='{}';
BEGIN
  IF jsonb_typeof(a) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
  IF op='company.upsert' THEN
    PERFORM {{tenantSchema}}.ac_catalog_operator(ctx);
    row:={{tenantSchema}}.ac_catalog_clean(a->'company','{"org_id":{"type":"text","default":null,"required":true,"nullable":false},"legal_name":{"type":"text","default":null,"required":true,"nullable":false},"register_id":{"type":"text","default":null,"required":false,"nullable":false},"address":{"type":"text","default":null,"required":false,"nullable":false},"iban":{"type":"text","default":null,"required":false,"nullable":false},"kyb_verified_by":{"type":"text","default":null,"required":false,"nullable":false},"roles":{"type":"texts","default":[],"required":false,"nullable":false},"categories":{"type":"texts","default":[],"required":false,"nullable":false},"kyb_verified":{"type":"bool","default":false,"required":false,"nullable":false},"spending_limit_minor":{"type":"int","default":0,"required":false,"nullable":false},"profile":{"type":"object","default":{},"required":false,"nullable":false}}'::jsonb);
    PERFORM {{tenantSchema}}.ac_catalog_put(t,'company',row->>'org_id',row);
    RETURN jsonb_build_object('org_id',row->>'org_id');
  ELSIF op='evaluator.upsert' THEN
    PERFORM {{tenantSchema}}.ac_catalog_operator(ctx);
    row:={{tenantSchema}}.ac_catalog_clean(a->'evaluator','{"evaluator_id":{"type":"text","default":null,"required":true,"nullable":false},"org_id":{"type":"text","default":null,"required":true,"nullable":false},"version":{"type":"positive","default":null,"required":true,"nullable":false},"did":{"type":"text","default":null,"required":false,"nullable":false},"description":{"type":"text","default":null,"required":false,"nullable":false},"deterministic":{"type":"bool","default":false,"required":false,"nullable":false},"accepts":{"type":"texts","default":[],"required":false,"nullable":false},"params_schema":{"type":"object","default":{},"required":false,"nullable":false}}'::jsonb);
    PERFORM {{tenantSchema}}.ac_catalog_put(t,'evaluator',jsonb_build_array(row->>'evaluator_id',row->'version')::text,row);
    RETURN jsonb_build_object('evaluator_id',row->>'evaluator_id','version',row->'version');
  ELSIF op='catalog.publish' THEN
    IF ctx->>'callerKind'<>'fenced_worker' THEN PERFORM {{tenantSchema}}.ac_catalog_error('forbidden'); END IF;
    ident:={{tenantSchema}}.ac_catalog_text(a,'seller_org_id');
    row:={{tenantSchema}}.ac_catalog_get(t,'company',ident);
    IF row IS NULL OR NOT row->'roles' ? 'seller' THEN PERFORM {{tenantSchema}}.ac_catalog_error('unknown_seller'); END IF;
    IF jsonb_typeof(a->'offers') IS DISTINCT FROM 'array' THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':catalog:'||ident,0));
    DELETE FROM {{tenantSchema}}.ac_catalog_records WHERE tenant_id=t AND kind='offer' AND doc->>'seller_org_id'=ident;
    FOR item IN SELECT value FROM jsonb_array_elements(a->'offers') LOOP
      IF item->>'seller_org_id' IS NOT NULL AND item->>'seller_org_id'<>ident THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
      row:={{tenantSchema}}.ac_catalog_clean(item||jsonb_build_object('seller_org_id',ident),'{"seller_org_id":{"type":"text","default":null,"required":true,"nullable":false},"offer_id":{"type":"text","default":null,"required":true,"nullable":false},"title":{"type":"text","default":null,"required":true,"nullable":false},"category":{"type":"text","default":null,"required":true,"nullable":false},"currency":{"type":"text","default":null,"required":true,"nullable":false},"description":{"type":"text","default":null,"required":false,"nullable":false},"price_minor":{"type":"int","default":null,"required":true,"nullable":false},"delivery_time_s":{"type":"int","default":null,"required":true,"nullable":false},"input_schema":{"type":"object","default":{},"required":false,"nullable":false},"deliverable":{"type":"object","default":{},"required":false,"nullable":false},"default_acceptance":{"type":"object","default":{},"required":false,"nullable":false},"active":{"type":"bool","default":true,"required":false,"nullable":false}}'::jsonb);
      IF row->>'offer_id'=ANY(ids) THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
      ids:=array_append(ids,row->>'offer_id');
      PERFORM {{tenantSchema}}.ac_catalog_put(t,'offer',jsonb_build_array(ident,row->>'offer_id')::text,row);
    END LOOP;
    RETURN jsonb_build_object('count',cardinality(ids));
  ELSIF op='company.read' THEN
    RETURN jsonb_build_object('company',{{tenantSchema}}.ac_catalog_get(t,'company',{{tenantSchema}}.ac_catalog_text(a,'org_id')));
  ELSIF op IN ('companies.list','sellers.list') THEN
    role_filter:=CASE WHEN op='sellers.list' THEN 'seller' ELSE {{tenantSchema}}.ac_catalog_text(a,'role',true) END;
    IF role_filter IS NOT NULL AND role_filter NOT IN ('buyer','seller') THEN PERFORM {{tenantSchema}}.ac_catalog_error('invalid_argument'); END IF;
    category:=CASE WHEN op='sellers.list' THEN {{tenantSchema}}.ac_catalog_text(a,'category',true) END;
    SELECT COALESCE(jsonb_agg(doc ORDER BY doc->>'org_id'),'[]') INTO result FROM {{tenantSchema}}.ac_catalog_records
      WHERE tenant_id=t AND kind='company' AND (role_filter IS NULL OR doc->'roles' ? role_filter) AND (category IS NULL OR doc->'categories' ? category);
    RETURN jsonb_build_object(CASE op WHEN 'sellers.list' THEN 'sellers' ELSE 'companies' END,result);
  ELSIF op='catalog.read' THEN
    ident:={{tenantSchema}}.ac_catalog_text(a,'seller_org_id');
    SELECT COALESCE(jsonb_agg(doc ORDER BY doc->>'offer_id'),'[]') INTO result FROM {{tenantSchema}}.ac_catalog_records WHERE tenant_id=t AND kind='offer' AND doc->>'seller_org_id'=ident;
    RETURN jsonb_build_object('offers',result);
  ELSIF op='evaluators.list' THEN
    SELECT COALESCE(jsonb_agg(doc ORDER BY doc->>'evaluator_id',(doc->>'version')::bigint),'[]') INTO result FROM {{tenantSchema}}.ac_catalog_records WHERE tenant_id=t AND kind='evaluator';
    RETURN jsonb_build_object('evaluators',result);
  END IF;
  PERFORM {{tenantSchema}}.ac_catalog_error('unknown_export');
END $$;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_error(text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_error(text) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_text(jsonb,text,boolean) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_text(jsonb,text,boolean) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_int(jsonb,text,bigint,bigint) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_int(jsonb,text,bigint,bigint) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_clean(jsonb,jsonb,boolean) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_clean(jsonb,jsonb,boolean) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_get(uuid,text,text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_get(uuid,text,text) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_put(uuid,text,text,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_put(uuid,text,text,jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_operator(jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_operator(jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_escrow(jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_escrow(jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_catalog_dispatch(jsonb,jsonb,text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_catalog_dispatch(jsonb,jsonb,text) FROM PUBLIC;
