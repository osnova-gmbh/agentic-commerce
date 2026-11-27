"""Native PostgreSQL implementations; generated bundles contain no Python callbacks.

Every row is tenant scoped. All exported calls are guarded by AgentDb's protected
module context, and domain roles are checked against deployment-owned settings.
The JSON carrier keeps the arbitrary signed body lossless within AgentDb's closed
schema dialect. It is decoded only inside the native function, never executed.
"""

import json

COMMON = r"""
CREATE TABLE {{tenantSchema}}.__P___records (
  tenant_id uuid NOT NULL, kind text NOT NULL, id text NOT NULL,
  doc jsonb NOT NULL CHECK (jsonb_typeof(doc) = 'object'),
  ordinal bigint GENERATED ALWAYS AS IDENTITY,
  PRIMARY KEY (tenant_id, kind, id)
);
ALTER TABLE {{tenantSchema}}.__P___records OWNER TO agentdb_owner;
REVOKE ALL ON {{tenantSchema}}.__P___records FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.__P___error(code text) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN RAISE EXCEPTION USING ERRCODE = 'P0200', MESSAGE = code; END $$;

CREATE FUNCTION {{tenantSchema}}.__P___text(v jsonb, k text, optional boolean DEFAULT false)
RETURNS text LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF optional AND (NOT v ? k OR v->k = 'null'::jsonb) THEN RETURN NULL; END IF;
  IF jsonb_typeof(v->k) IS DISTINCT FROM 'string' OR length(v->>k)=0 THEN
    PERFORM {{tenantSchema}}.__P___error('invalid_argument');
  END IF;
  RETURN v->>k;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___int(v jsonb, k text, fallback bigint DEFAULT NULL, minimum bigint DEFAULT 0)
RETURNS bigint LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE n bigint;
BEGIN
  IF NOT v ? k OR v->k='null'::jsonb THEN n:=fallback;
  ELSIF jsonb_typeof(v->k)='number' AND (v->>k) ~ '^-?[0-9]+$' THEN n:=(v->>k)::bigint;
  ELSE PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  IF n IS NULL OR n<minimum THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  RETURN n;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___clean(v jsonb, rules jsonb, partial boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE result jsonb:='{}'; k text; r jsonb; item jsonb; typ text; valid boolean;
BEGIN
  IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(v) x WHERE NOT rules ? x) THEN
    PERFORM {{tenantSchema}}.__P___error('invalid_argument');
  END IF;
  FOR k,r IN SELECT key,value FROM jsonb_each(rules) LOOP
    IF partial AND NOT v ? k THEN CONTINUE; END IF;
    item:=v->k;
    IF item IS NULL OR item='null'::jsonb THEN
      IF COALESCE((r->>'required')::boolean,false) THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
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
    IF NOT valid THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
    result:=result||jsonb_build_object(k,item);
  END LOOP;
  RETURN result;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___get(t uuid, k text, ident text) RETURNS jsonb
LANGUAGE sql SET search_path = pg_catalog AS $$
  SELECT doc FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind=k AND id=ident;
$$;

CREATE FUNCTION {{tenantSchema}}.__P___put(t uuid,k text,ident text,value jsonb) RETURNS void
LANGUAGE sql SET search_path = pg_catalog AS $$
  INSERT INTO {{tenantSchema}}.__P___records(tenant_id,kind,id,doc) VALUES(t,k,ident,value)
  ON CONFLICT(tenant_id,kind,id) DO UPDATE SET doc=excluded.doc;
$$;

CREATE FUNCTION {{tenantSchema}}.__P___operator(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ((ctx->>'callerKind'='tenant_client'
      AND NULLIF(ctx#>>'{settings,operator_principal_id}','') IS NOT NULL
      AND ctx->>'principalId'=ctx#>>'{settings,operator_principal_id}')
    OR (ctx->>'callerKind'='fenced_worker' AND ctx->>'installationId'=ctx#>>'{settings,escrow_installation_id}')) IS NOT TRUE THEN
    PERFORM {{tenantSchema}}.__P___error('forbidden');
  END IF;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___escrow(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ctx->>'callerKind' IS DISTINCT FROM 'fenced_worker'
     OR ctx->>'installationId' IS DISTINCT FROM ctx#>>'{settings,escrow_installation_id}' THEN
    PERFORM {{tenantSchema}}.__P___error('forbidden');
  END IF;
END $$;
"""


def rule(kind, default=None, required=False, nullable=False, enum=None):
    out = {"type": kind, "default": default, "required": required, "nullable": nullable}
    if enum is not None:
        out["enum"] = enum
    return out


COMPANY = {
    "org_id": rule("text", required=True),
    "legal_name": rule("text", required=True),
    **{
        key: rule("text")
        for key in ("register_id", "address", "iban", "kyb_verified_by")
    },
    "roles": rule("texts", []),
    "categories": rule("texts", []),
    "kyb_verified": rule("bool", False),
    "spending_limit_minor": rule("int", 0),
    "profile": rule("object", {}),
}
OFFER = {
    **{
        key: rule("text", required=True)
        for key in ("seller_org_id", "offer_id", "title", "category", "currency")
    },
    "description": rule("text"),
    "price_minor": rule("int", required=True),
    "delivery_time_s": rule("int", required=True),
    **{
        key: rule("object", {})
        for key in ("input_schema", "deliverable", "default_acceptance")
    },
    "active": rule("bool", True),
}
EVALUATOR = {
    **{key: rule("text", required=True) for key in ("evaluator_id", "org_id")},
    "version": rule("positive", required=True),
    "did": rule("text"),
    "description": rule("text"),
    "deterministic": rule("bool", False),
    "accepts": rule("texts", []),
    "params_schema": rule("object", {}),
}

CATALOG = r"""
CREATE FUNCTION {{tenantSchema}}.__P___dispatch(ctx jsonb,a jsonb,op text) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; row jsonb; item jsonb; result jsonb; ident text; role_filter text; category text; ids text[]:='{}';
BEGIN
  IF jsonb_typeof(a) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  IF op='company.upsert' THEN
    PERFORM {{tenantSchema}}.__P___operator(ctx);
    row:={{tenantSchema}}.__P___clean(a->'company','__COMPANY__'::jsonb);
    PERFORM {{tenantSchema}}.__P___put(t,'company',row->>'org_id',row);
    RETURN jsonb_build_object('org_id',row->>'org_id');
  ELSIF op='evaluator.upsert' THEN
    PERFORM {{tenantSchema}}.__P___operator(ctx);
    row:={{tenantSchema}}.__P___clean(a->'evaluator','__EVALUATOR__'::jsonb);
    PERFORM {{tenantSchema}}.__P___put(t,'evaluator',jsonb_build_array(row->>'evaluator_id',row->'version')::text,row);
    RETURN jsonb_build_object('evaluator_id',row->>'evaluator_id','version',row->'version');
  ELSIF op='catalog.publish' THEN
    IF ctx->>'callerKind'<>'fenced_worker' THEN PERFORM {{tenantSchema}}.__P___error('forbidden'); END IF;
    ident:={{tenantSchema}}.__P___text(a,'seller_org_id');
    row:={{tenantSchema}}.__P___get(t,'company',ident);
    IF row IS NULL OR NOT row->'roles' ? 'seller' THEN PERFORM {{tenantSchema}}.__P___error('unknown_seller'); END IF;
    IF jsonb_typeof(a->'offers') IS DISTINCT FROM 'array' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':catalog:'||ident,0));
    DELETE FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='offer' AND doc->>'seller_org_id'=ident;
    FOR item IN SELECT value FROM jsonb_array_elements(a->'offers') LOOP
      IF item->>'seller_org_id' IS NOT NULL AND item->>'seller_org_id'<>ident THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
      row:={{tenantSchema}}.__P___clean(item||jsonb_build_object('seller_org_id',ident),'__OFFER__'::jsonb);
      IF row->>'offer_id'=ANY(ids) THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
      ids:=array_append(ids,row->>'offer_id');
      PERFORM {{tenantSchema}}.__P___put(t,'offer',jsonb_build_array(ident,row->>'offer_id')::text,row);
    END LOOP;
    RETURN jsonb_build_object('count',cardinality(ids));
  ELSIF op='company.read' THEN
    RETURN jsonb_build_object('company',{{tenantSchema}}.__P___get(t,'company',{{tenantSchema}}.__P___text(a,'org_id')));
  ELSIF op IN ('companies.list','sellers.list') THEN
    role_filter:=CASE WHEN op='sellers.list' THEN 'seller' ELSE {{tenantSchema}}.__P___text(a,'role',true) END;
    IF role_filter IS NOT NULL AND role_filter NOT IN ('buyer','seller') THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
    category:=CASE WHEN op='sellers.list' THEN {{tenantSchema}}.__P___text(a,'category',true) END;
    SELECT COALESCE(jsonb_agg(doc ORDER BY doc->>'org_id'),'[]') INTO result FROM {{tenantSchema}}.__P___records
      WHERE tenant_id=t AND kind='company' AND (role_filter IS NULL OR doc->'roles' ? role_filter) AND (category IS NULL OR doc->'categories' ? category);
    RETURN jsonb_build_object(CASE op WHEN 'sellers.list' THEN 'sellers' ELSE 'companies' END,result);
  ELSIF op='catalog.read' THEN
    ident:={{tenantSchema}}.__P___text(a,'seller_org_id');
    SELECT COALESCE(jsonb_agg(doc ORDER BY doc->>'offer_id'),'[]') INTO result FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='offer' AND doc->>'seller_org_id'=ident;
    RETURN jsonb_build_object('offers',result);
  ELSIF op='evaluators.list' THEN
    SELECT COALESCE(jsonb_agg(doc ORDER BY doc->>'evaluator_id',(doc->>'version')::bigint),'[]') INTO result FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='evaluator';
    RETURN jsonb_build_object('evaluators',result);
  END IF;
  PERFORM {{tenantSchema}}.__P___error('unknown_export');
END $$;
"""


def native_sql(module):
    prefix = {
        "cogit-finance-catalog": "ac_catalog",
        "cogit-finance-deals": "ac_deals",
        "cogit-messaging": "ac_msg",
    }[module]
    source = (
        COMMON
        + {
            "cogit-finance-catalog": CATALOG,
            "cogit-finance-deals": DEALS,
            "cogit-messaging": MESSAGING,
        }[module]
    )
    for name, spec in {
        "COMPANY": COMPANY,
        "OFFER": OFFER,
        "EVALUATOR": EVALUATOR,
        **DEAL_SPECS,
    }.items():
        source = source.replace(f"__{name}__", json.dumps(spec, separators=(",", ":")))
    source = source.replace("__P__", prefix)
    # Internal helpers cannot be invoked by clients, even if they guess names.
    import re

    functions = re.findall(
        r"CREATE FUNCTION \{\{tenantSchema\}\}\.([a-z_]+)\((.*?)\)\s*RETURNS",
        source,
        re.S,
    )
    for name, arguments in functions:
        types = [part.strip().split()[1] for part in arguments.split(",")]
        signature = f"{{{{tenantSchema}}}}.{name}({','.join(types)})"
        source += f"\nALTER FUNCTION {signature} OWNER TO agentdb_owner;\nREVOKE ALL ON FUNCTION {signature} FROM PUBLIC;\n"
    return source


DEAL_SPECS = {
    "DELIVERIES": {
        **{
            key: rule("text", required=True)
            for key in (
                "delivery_id",
                "artifact_id",
                "sha256",
                "media_type",
                "delivered_at",
            )
        },
        "attempt": rule("positive", required=True),
        "byte_length": rule("int", required=True),
        "status": rule("text", "delivered"),
    },
    "EVALUATIONS": {
        **{
            key: rule("text", required=True)
            for key in (
                "evaluation_request_id",
                "delivery_id",
                "evaluator_id",
                "evaluator_did",
                "respond_by",
            )
        },
        "evaluator_version": rule("int", required=True),
        "resends": rule("int", 0),
        "verdict_message_id": rule("text", nullable=True),
        "outcome": rule("text", nullable=True, enum=["pass", "fail", "error"]),
    },
    "INTENTS": {
        **{
            key: rule("text", required=True)
            for key in ("intent_id", "currency", "to_iban")
        },
        "kind": rule(
            "text", required=True, enum=["payout", "fee", "refund", "return_unmatched"]
        ),
        "amount_minor": rule("int", required=True),
        "status": rule(
            "text",
            "prepared",
            enum=["prepared", "submitted", "unknown", "confirmed", "failed"],
        ),
        "bank_ref": rule("text", nullable=True),
    },
    "CREDITS": {
        **{
            key: rule("text", required=True)
            for key in ("bank_event_id", "reference", "from_iban", "received_at")
        },
        "amount_minor": rule("int", required=True),
        "disposition": rule("text", required=True, enum=["funded", "returned"]),
    },
    "POSTINGS": {
        **{key: rule("text", required=True) for key in ("posting_id", "source_id")},
        "account": rule(
            "text",
            required=True,
            enum=["held", "seller", "fee", "buyer_refund", "returned"],
        ),
        "amount_minor": rule("signed", required=True),
    },
}

DEALS = r"""
CREATE UNIQUE INDEX ac_deals_hash ON {{tenantSchema}}.__P___records(tenant_id,(doc->>'hash')) WHERE kind='event';
CREATE UNIQUE INDEX ac_deals_source ON {{tenantSchema}}.__P___records(tenant_id,(doc->>'source_message_id')) WHERE kind='event' AND doc->>'source_message_id' IS NOT NULL;
CREATE UNIQUE INDEX ac_deals_posting ON {{tenantSchema}}.__P___records(tenant_id,(doc->>'source_id'),(doc->>'account')) WHERE kind='posting';
CREATE UNIQUE INDEX ac_deals_active_intent ON {{tenantSchema}}.__P___records(tenant_id,(doc->>'deal_id'))
 WHERE kind='intent' AND doc->>'kind' IN ('payout','refund') AND doc->>'status' IN ('prepared','submitted','unknown');
CREATE INDEX ac_deals_by_deal ON {{tenantSchema}}.__P___records(tenant_id,kind,(doc->>'deal_id'));

CREATE FUNCTION {{tenantSchema}}.__P___row(t uuid,k text,deal text,item jsonb,merge_rows boolean,stamp text) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE rules jsonb; keyname text; ident text; old jsonb; row jsonb; failure text;
BEGIN
  CASE k
    WHEN 'delivery' THEN rules:='__DELIVERIES__'; keyname:='delivery_id'; failure:='invalid_argument';
    WHEN 'evaluation' THEN rules:='__EVALUATIONS__'; keyname:='evaluation_request_id'; failure:='invalid_argument';
    WHEN 'intent' THEN rules:='__INTENTS__'; keyname:='intent_id'; failure:='intent_conflict';
    WHEN 'credit' THEN rules:='__CREDITS__'; keyname:='bank_event_id'; failure:='duplicate_credit';
    WHEN 'posting' THEN rules:='__POSTINGS__'; keyname:='posting_id'; failure:='duplicate_posting';
    ELSE PERFORM {{tenantSchema}}.__P___error('invalid_argument');
  END CASE;
  IF item->>'deal_id' IS NOT NULL AND item->>'deal_id'<>deal THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  ident:={{tenantSchema}}.__P___text(item,keyname);
  old:={{tenantSchema}}.__P___get(t,k,ident);
  IF old IS NOT NULL AND NOT merge_rows THEN PERFORM {{tenantSchema}}.__P___error(failure); END IF;
  IF old IS NOT NULL AND old->>'deal_id'<>deal THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  row:={{tenantSchema}}.__P___clean(item-'deal_id',rules,old IS NOT NULL);
  row:=COALESCE(old,'{}')||row||jsonb_build_object('deal_id',deal);
  IF k='evaluation' AND NOT EXISTS(SELECT 1 FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='delivery' AND id=row->>'delivery_id' AND doc->>'deal_id'=deal) THEN
    PERFORM {{tenantSchema}}.__P___error('invalid_argument');
  END IF;
  IF k IN ('intent','posting') AND old IS NULL THEN row:=row||jsonb_build_object('created_at',stamp); END IF;
  IF k='intent' THEN row:=row||jsonb_build_object('updated_at',stamp); END IF;
  BEGIN
    IF merge_rows THEN PERFORM {{tenantSchema}}.__P___put(t,k,ident,row);
    ELSE INSERT INTO {{tenantSchema}}.__P___records(tenant_id,kind,id,doc) VALUES(t,k,ident,row); END IF;
  EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.__P___error(failure);
  END;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___commit(ctx jsonb,a jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; ident text; expected bigint; previous text; ev jsonb; fields jsonb;
  old jsonb; known jsonb; stamp text:=to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"');
  key text; item jsonb; array_name text; kind_name text; position bigint:=0; outbox_id text; row jsonb;
BEGIN
  PERFORM {{tenantSchema}}.__P___escrow(ctx);
  IF EXISTS(SELECT 1 FROM jsonb_object_keys(a) k WHERE k NOT IN ('deal_id','expected_seq','expected_hash','event','deal','outbox','deliveries','evaluations','intents','credits','postings')) THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  ident:={{tenantSchema}}.__P___text(a,'deal_id'); expected:={{tenantSchema}}.__P___int(a,'expected_seq'); previous:={{tenantSchema}}.__P___text(a,'expected_hash');
  ev:=a->'event'; fields:=COALESCE(NULLIF(a->'deal','null'),'{}');
  IF jsonb_typeof(ev) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(ev) k WHERE k NOT IN ('deal_id','seq','prev_hash','hash','event_type','actor_did','body','state_after','source_message_id'))
    OR ev->>'deal_id' IS NOT NULL AND ev->>'deal_id'<>ident THEN PERFORM {{tenantSchema}}.__P___error('bad_event'); END IF;
  IF jsonb_typeof(fields)<>'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(fields) k WHERE k NOT IN ('deal_id','buyer_org_id','seller_org_id','offer_id','terms','terms_hash')) THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  FOREACH key IN ARRAY ARRAY['prev_hash','hash','event_type','actor_did','state_after'] LOOP
    IF jsonb_typeof(ev->key) IS DISTINCT FROM 'string' OR length(ev->>key)=0 THEN PERFORM {{tenantSchema}}.__P___error('bad_event'); END IF;
  END LOOP;
  IF ev->>'hash' !~ '^[0-9a-f]{64}$' OR ev->>'prev_hash' !~ '^[0-9a-f]{64}$'
    OR jsonb_typeof(ev->'body') IS DISTINCT FROM 'object' OR jsonb_typeof(ev->'seq') IS DISTINCT FROM 'number'
    OR ev->>'seq' !~ '^[1-9][0-9]*$' THEN PERFORM {{tenantSchema}}.__P___error('bad_event'); END IF;
  IF ev->'source_message_id' IS NOT NULL AND ev->'source_message_id'<>'null'::jsonb AND
    (jsonb_typeof(ev->'source_message_id')<>'string' OR ev->>'source_message_id'='') THEN PERFORM {{tenantSchema}}.__P___error('bad_event'); END IF;
  FOREACH key IN ARRAY ARRAY['buyer_org_id','seller_org_id','offer_id'] LOOP
    IF fields->key IS NOT NULL AND fields->key<>'null'::jsonb THEN PERFORM {{tenantSchema}}.__P___text(fields,key); END IF;
  END LOOP;
  IF fields->'terms' IS NOT NULL AND fields->'terms'<>'null'::jsonb AND jsonb_typeof(fields->'terms')<>'object' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  IF fields->>'terms_hash' IS NOT NULL AND fields->>'terms_hash' !~ '^[0-9a-f]{64}$' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  FOREACH key IN ARRAY ARRAY['outbox','deliveries','evaluations','intents','credits','postings'] LOOP
    IF jsonb_typeof(COALESCE(NULLIF(a->key,'null'),'[]'))<>'array' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  END LOOP;
  PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':deal:'||ident,0));
  IF ev->>'source_message_id' IS NOT NULL THEN
    SELECT doc INTO known FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='event' AND doc->>'source_message_id'=ev->>'source_message_id';
    IF known IS NOT NULL THEN
      IF known->>'deal_id'<>ident THEN PERFORM {{tenantSchema}}.__P___error('bad_event'); END IF;
      RETURN jsonb_build_object('seq',known->'seq','hash',known->'hash','duplicate',true);
    END IF;
  END IF;
  old:={{tenantSchema}}.__P___get(t,'deal',ident);
  IF expected<>COALESCE((old->>'head_seq')::bigint,0) OR previous<>COALESCE(old->>'head_hash',repeat('0',64)) THEN PERFORM {{tenantSchema}}.__P___error('head_mismatch'); END IF;
  IF old IS NULL THEN
    FOREACH key IN ARRAY ARRAY['buyer_org_id','seller_org_id','offer_id'] LOOP
      IF fields->>key IS NULL THEN PERFORM {{tenantSchema}}.__P___error('head_mismatch'); END IF;
    END LOOP;
    old:=jsonb_build_object('deal_id',ident,'buyer_org_id',fields->'buyer_org_id','seller_org_id',fields->'seller_org_id','offer_id',fields->'offer_id','created_at',stamp,'terms',NULL,'terms_hash',NULL);
  ELSE
    FOREACH key IN ARRAY ARRAY['buyer_org_id','seller_org_id','offer_id'] LOOP
      IF fields->>key IS NOT NULL AND fields->key<>old->key THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
    END LOOP;
  END IF;
  IF (ev->>'seq')::bigint<>expected+1 OR ev->>'prev_hash'<>previous THEN PERFORM {{tenantSchema}}.__P___error('bad_event'); END IF;
  row:=old||jsonb_build_object('state',ev->'state_after','head_seq',ev->'seq','head_hash',ev->'hash','updated_at',stamp);
  FOREACH key IN ARRAY ARRAY['terms','terms_hash'] LOOP
    IF fields->key IS NOT NULL AND fields->key<>'null'::jsonb THEN row:=row||jsonb_build_object(key,fields->key); END IF;
  END LOOP;
  PERFORM {{tenantSchema}}.__P___put(t,'deal',ident,row);
  BEGIN
    INSERT INTO {{tenantSchema}}.__P___records(tenant_id,kind,id,doc)
      VALUES(t,'event',jsonb_build_array(ident,ev->'seq')::text,ev||jsonb_build_object('deal_id',ident,'source_message_id',ev->'source_message_id','recorded_at',stamp));
  EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.__P___error('bad_event'); END;
  FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(NULLIF(a->'outbox','null'),'[]')) LOOP
    IF jsonb_typeof(item)<>'object' OR item-'deal_id'-'outbox_id'-'envelope'<>'{}' OR jsonb_typeof(item->'envelope') IS DISTINCT FROM 'object' OR item->>'deal_id' IS NOT NULL AND item->>'deal_id'<>ident THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
    outbox_id:={{tenantSchema}}.__P___text(item,'outbox_id');
    BEGIN
      INSERT INTO {{tenantSchema}}.__P___records(tenant_id,kind,id,doc) VALUES(t,'outbox',outbox_id,
        jsonb_build_object('outbox_id',outbox_id,'deal_id',ident,'seq',ev->'seq','envelope',item->'envelope','status','pending','sent_at',NULL,'created_at',stamp,'ordinal',position));
    EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END;
    position:=position+1;
  END LOOP;
  FOR array_name,kind_name IN SELECT * FROM (VALUES('deliveries','delivery'),('evaluations','evaluation'),('intents','intent'),('credits','credit'),('postings','posting')) AS kinds(a,b) LOOP
    FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(NULLIF(a->array_name,'null'),'[]')) LOOP
      PERFORM {{tenantSchema}}.__P___row(t,kind_name,ident,item,kind_name IN ('delivery','evaluation'),stamp);
    END LOOP;
  END LOOP;
  RETURN jsonb_build_object('seq',ev->'seq','hash',ev->'hash','duplicate',false);
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___dispatch(ctx jsonb,a jsonb,op text) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; ident text; row jsonb; item jsonb; result jsonb; n bigint;
  stamp text:=to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'); key text; kind_name text;
BEGIN
  IF jsonb_typeof(a) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  IF op='deal.commit' THEN RETURN {{tenantSchema}}.__P___commit(ctx,a);
  ELSIF op IN ('outbox.mark_sent','intent.update') THEN
    PERFORM {{tenantSchema}}.__P___escrow(ctx);
    IF op='outbox.mark_sent' THEN
      ident:={{tenantSchema}}.__P___text(a,'outbox_id');
      UPDATE {{tenantSchema}}.__P___records SET doc=doc||jsonb_build_object('status','sent','sent_at',stamp) WHERE tenant_id=t AND kind='outbox' AND id=ident AND doc->>'status'='pending';
    ELSE
      ident:={{tenantSchema}}.__P___text(a,'intent_id');
      PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':intent:'||ident,0));
      row:={{tenantSchema}}.__P___get(t,'intent',ident);
      IF row IS NULL THEN PERFORM {{tenantSchema}}.__P___error('unknown_intent'); END IF;
      IF a->>'status' IS NULL OR a->>'status' NOT IN ('prepared','submitted','unknown','confirmed','failed') THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
      row:=row||jsonb_build_object('status',a->'status','updated_at',stamp);
      IF a->>'bank_ref' IS NOT NULL THEN row:=row||jsonb_build_object('bank_ref',{{tenantSchema}}.__P___text(a,'bank_ref')); END IF;
      BEGIN PERFORM {{tenantSchema}}.__P___put(t,'intent',ident,row);
      EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.__P___error('intent_conflict'); END;
      IF jsonb_typeof(COALESCE(NULLIF(a->'postings','null'),'[]'))<>'array' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
      FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(NULLIF(a->'postings','null'),'[]')) LOOP
        item:=jsonb_build_object('source_id',ident)||item;
        PERFORM {{tenantSchema}}.__P___clean(item-'deal_id','__POSTINGS__'::jsonb,true);
        IF NOT EXISTS(SELECT 1 FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='posting' AND doc->>'source_id'=item->>'source_id' AND doc->>'account'=item->>'account') THEN
          PERFORM {{tenantSchema}}.__P___row(t,'posting',row->>'deal_id',item,false,stamp);
        END IF;
      END LOOP;
    END IF;
    RETURN '{}';
  ELSIF op='outbox.pending' THEN
    n:={{tenantSchema}}.__P___int(a,'limit',50);
    SELECT COALESCE(jsonb_agg(x.doc ORDER BY x.created,x.deal,x.seq,x.position,x.id),'[]') INTO result FROM (
      SELECT doc-'status'-'sent_at'-'created_at'-'ordinal' AS doc,doc->>'created_at' created,doc->>'deal_id' deal,(doc->>'seq')::bigint seq,(doc->>'ordinal')::bigint position,id
      FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='outbox' AND doc->>'status'='pending'
      ORDER BY created,deal,seq,position,id LIMIT n) x;
    RETURN jsonb_build_object('entries',result);
  ELSIF op='deal.list' THEN
    SELECT COALESCE(jsonb_agg(jsonb_build_object('deal_id',doc->'deal_id','state',doc->'state','buyer_org_id',doc->'buyer_org_id','seller_org_id',doc->'seller_org_id','offer_id',doc->'offer_id','head_seq',doc->'head_seq','price_minor',doc#>'{terms,price_minor}','currency',doc#>'{terms,currency}','created_at',doc->'created_at','updated_at',doc->'updated_at') ORDER BY doc->>'created_at' DESC,doc->>'updated_at' DESC,id),'[]')
      INTO result FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='deal';
    RETURN jsonb_build_object('deals',result);
  ELSIF op='deal.read' THEN
    ident:={{tenantSchema}}.__P___text(a,'deal_id');
    result:=jsonb_build_object('deal',{{tenantSchema}}.__P___get(t,'deal',ident));
    FOR key,kind_name IN SELECT * FROM (VALUES('events','event'),('deliveries','delivery'),('evaluations','evaluation'),('intents','intent'),('credits','credit')) AS kinds(a,b) LOOP
      SELECT COALESCE(jsonb_agg(CASE kind_name WHEN 'evaluation' THEN r.doc-'deal_id' ELSE r.doc END ORDER BY
        CASE kind_name WHEN 'event' THEN (r.doc->>'seq')::bigint WHEN 'delivery' THEN (r.doc->>'attempt')::bigint WHEN 'evaluation' THEN ({{tenantSchema}}.__P___get(t,'delivery',r.doc->>'delivery_id')->>'attempt')::bigint END,
        CASE kind_name WHEN 'intent' THEN r.doc->>'created_at' WHEN 'credit' THEN r.doc->>'received_at' ELSE r.doc->>'delivery_id' END,r.id),'[]')
        INTO item FROM {{tenantSchema}}.__P___records r WHERE tenant_id=t AND kind=kind_name AND doc->>'deal_id'=ident;
      result:=result||jsonb_build_object(key,item);
    END LOOP;
    RETURN result;
  ELSIF op='ledger.balances' THEN
    ident:={{tenantSchema}}.__P___text(a,'deal_id',true); result:='{}';
    FOREACH key IN ARRAY ARRAY['held','seller','fee','buyer_refund','returned'] LOOP
      SELECT COALESCE(sum((doc->>'amount_minor')::bigint),0) INTO n FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='posting' AND doc->>'account'=key AND (ident IS NULL OR doc->>'deal_id'=ident);
      result:=result||jsonb_build_object(key,n);
    END LOOP;
    RETURN result;
  END IF;
  PERFORM {{tenantSchema}}.__P___error('unknown_export');
END $$;
"""
MESSAGING = r"""
CREATE INDEX ac_msg_inbox ON {{tenantSchema}}.__P___records(tenant_id,(doc->>'recipient_did'),ordinal) WHERE kind='message';
CREATE INDEX ac_msg_conversation ON {{tenantSchema}}.__P___records(tenant_id,(doc->>'conversation_id'),ordinal) WHERE kind='message';

CREATE FUNCTION {{tenantSchema}}.__P___no_float(v jsonb) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE item jsonb;
BEGIN
  IF jsonb_typeof(v)='number' THEN RETURN (v#>>'{}') ~ '^-?[0-9]+$'; END IF;
  IF jsonb_typeof(v)='array' THEN
    FOR item IN SELECT value FROM jsonb_array_elements(v) LOOP IF NOT {{tenantSchema}}.__P___no_float(item) THEN RETURN false; END IF; END LOOP;
  ELSIF jsonb_typeof(v)='object' THEN
    FOR item IN SELECT value FROM jsonb_each(v) LOOP IF NOT {{tenantSchema}}.__P___no_float(item) THEN RETURN false; END IF; END LOOP;
  END IF;
  RETURN true;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___schema(s jsonb,depth integer DEFAULT 0) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE k text; item jsonb; typ jsonb;
BEGIN
  IF depth>12 OR jsonb_typeof(s) IS DISTINCT FROM 'object' OR NOT {{tenantSchema}}.__P___no_float(s)
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
    FOR item IN SELECT value FROM jsonb_each(s->'properties') LOOP IF NOT {{tenantSchema}}.__P___schema(item,depth+1) THEN RETURN false; END IF; END LOOP;
  END IF;
  IF s ? 'items' AND NOT {{tenantSchema}}.__P___schema(s->'items',depth+1) THEN RETURN false; END IF;
  RETURN true;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___matches(s jsonb,v jsonb,depth integer DEFAULT 0) RETURNS boolean
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
        IF NOT {{tenantSchema}}.__P___matches(s->'properties'->k,item,depth+1) THEN RETURN false; END IF;
      ELSIF s->'additionalProperties'='false'::jsonb THEN RETURN false; END IF;
    END LOOP;
  ELSIF typ='array' THEN
    IF s ? 'minItems' AND jsonb_array_length(v)<(s->>'minItems')::numeric OR s ? 'maxItems' AND jsonb_array_length(v)>(s->>'maxItems')::numeric THEN RETURN false; END IF;
    IF s ? 'items' THEN FOR item IN SELECT value FROM jsonb_array_elements(v) LOOP IF NOT {{tenantSchema}}.__P___matches(s->'items',item,depth+1) THEN RETURN false; END IF; END LOOP; END IF;
  ELSIF typ='string' THEN
    IF s ? 'minLength' AND length(v#>>'{}')<(s->>'minLength')::numeric OR s ? 'maxLength' AND length(v#>>'{}')>(s->>'maxLength')::numeric THEN RETURN false; END IF;
  ELSIF typ='number' THEN
    IF s ? 'minimum' AND (v#>>'{}')::numeric<(s->>'minimum')::numeric OR s ? 'maximum' AND (v#>>'{}')::numeric>(s->>'maximum')::numeric THEN RETURN false; END IF;
  END IF;
  RETURN true;
END $$;

CREATE FUNCTION {{tenantSchema}}.__P___dispatch(ctx jsonb,a jsonb,op text) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; installation text:=ctx->>'installationId'; k text; ident text; row jsonb; item jsonb; env jsonb;
  result jsonb; schema_doc jsonb; n bigint; version bigint; delay_s bigint; rec record;
  moment timestamptz:=clock_timestamp(); stamp text:=to_char(moment AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'); stale text;
  maximum bigint:=COALESCE((ctx#>>'{settings,max_delivery_attempts}')::bigint,5);
BEGIN
  IF jsonb_typeof(a) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
  IF op='identity.register' THEN
    PERFORM {{tenantSchema}}.__P___operator(ctx);
    ident:={{tenantSchema}}.__P___text(a,'did');
    PERFORM {{tenantSchema}}.__P___text(a,'installation_id'); PERFORM {{tenantSchema}}.__P___text(a,'org_id');
    IF a->>'role' IS NULL OR a->>'role' NOT IN ('buyer','seller','evaluator','escrow') THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
    row:={{tenantSchema}}.__P___get(t,'identity',ident);
    PERFORM {{tenantSchema}}.__P___put(t,'identity',ident,jsonb_build_object('did',ident,'installation_id',a->'installation_id','org_id',a->'org_id','role',a->'role','active',true,'registered_at',COALESCE(row->>'registered_at',stamp)));
    RETURN jsonb_build_object('did',ident);
  ELSIF op='identity.resolve' THEN
    IF a->>'did' IS NOT NULL THEN row:={{tenantSchema}}.__P___get(t,'identity',a->>'did');
    ELSIF a->>'role' IS NOT NULL THEN
      SELECT doc INTO row FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='identity' AND doc->'active'='true'::jsonb AND doc->>'role'=a->>'role' AND (a->>'org_id' IS NULL OR doc->>'org_id'=a->>'org_id') ORDER BY doc->>'registered_at',id LIMIT 1;
    ELSE PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
    RETURN jsonb_build_object('identity',CASE WHEN row->'active'='true'::jsonb THEN row ELSE NULL END);
  ELSIF op='type.register' THEN
    PERFORM {{tenantSchema}}.__P___escrow(ctx);
    ident:={{tenantSchema}}.__P___text(a,'type_key'); version:={{tenantSchema}}.__P___int(a,'type_version',NULL,1);
    schema_doc:=a->'json_schema';
    IF NOT {{tenantSchema}}.__P___schema(schema_doc) THEN PERFORM {{tenantSchema}}.__P___error('unsupported_schema'); END IF;
    k:=jsonb_build_array(ident,version)::text;
    PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':type:'||k,0));
    row:={{tenantSchema}}.__P___get(t,'type',k);
    IF row IS NULL THEN
      PERFORM {{tenantSchema}}.__P___put(t,'type',k,jsonb_build_object('type_key',ident,'type_version',version,'json_schema',schema_doc,'registered_by',installation,'registered_at',stamp));
      RETURN '{"status":"created"}';
    ELSIF row->'json_schema'=schema_doc THEN RETURN '{"status":"unchanged"}';
    ELSE PERFORM {{tenantSchema}}.__P___error('type_conflict'); END IF;
  ELSIF op='message.send' THEN
    env:=a->'envelope';
    IF jsonb_typeof(env) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.__P___error('invalid_envelope'); END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(env))<>11 OR NOT env ?& ARRAY['envelope_version','message_id','type_key','type_version','sender_did','recipient_did','conversation_id','causation_id','created_at','body','signature']
      OR env->'envelope_version'<>'1'::jsonb OR NOT {{tenantSchema}}.__P___no_float(env) THEN PERFORM {{tenantSchema}}.__P___error('invalid_envelope'); END IF;
    FOREACH k IN ARRAY ARRAY['message_id','type_key','sender_did','recipient_did','conversation_id','signature'] LOOP
      IF jsonb_typeof(env->k) IS DISTINCT FROM 'string' OR length(env->>k) NOT BETWEEN 1 AND 512 THEN PERFORM {{tenantSchema}}.__P___error('invalid_envelope'); END IF;
    END LOOP;
    IF jsonb_typeof(env->'type_version') IS DISTINCT FROM 'number' OR env->>'type_version' !~ '^[1-9][0-9]*$'
      OR jsonb_typeof(env->'body') IS DISTINCT FROM 'object' OR jsonb_typeof(env->'created_at') IS DISTINCT FROM 'string' OR env->>'created_at' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'
      OR (env->'causation_id'<>'null'::jsonb AND (jsonb_typeof(env->'causation_id')<>'string' OR env->>'causation_id'='')) THEN PERFORM {{tenantSchema}}.__P___error('invalid_envelope'); END IF;
    row:={{tenantSchema}}.__P___get(t,'identity',env->>'sender_did');
    IF ctx->>'callerKind'<>'fenced_worker' OR row->>'installation_id' IS DISTINCT FROM installation OR row->'active' IS DISTINCT FROM 'true'::jsonb THEN PERFORM {{tenantSchema}}.__P___error('not_your_did'); END IF;
    ident:=env->>'message_id';
    PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':message:'||ident,0));
    IF {{tenantSchema}}.__P___get(t,'message',ident) IS NOT NULL THEN RETURN jsonb_build_object('message_id',ident,'status','duplicate'); END IF;
    row:={{tenantSchema}}.__P___get(t,'identity',env->>'recipient_did');
    IF row->'active' IS DISTINCT FROM 'true'::jsonb THEN PERFORM {{tenantSchema}}.__P___error('unknown_recipient'); END IF;
    row:={{tenantSchema}}.__P___get(t,'type',jsonb_build_array(env->>'type_key',env->'type_version')::text);
    IF row IS NULL THEN PERFORM {{tenantSchema}}.__P___error('unknown_type'); END IF;
    IF NOT {{tenantSchema}}.__P___matches(row->'json_schema',env->'body') THEN PERFORM {{tenantSchema}}.__P___error('invalid_body'); END IF;
    INSERT INTO {{tenantSchema}}.__P___records(tenant_id,kind,id,doc) VALUES(t,'message',ident,
      jsonb_build_object('message_id',ident,'conversation_id',env->'conversation_id','causation_id',env->'causation_id','type_key',env->'type_key','type_version',env->'type_version','sender_did',env->'sender_did','recipient_did',env->'recipient_did','envelope',env,'status','queued','attempts',0,'available_at',stamp,'created_at',stamp,'claimed_at',NULL,'admission_key',NULL,'run_id',NULL,'reason',NULL,'acked_at',NULL));
    RETURN jsonb_build_object('message_id',ident,'status','queued');
  ELSIF op='message.claim' THEN
    IF ctx->>'callerKind'<>'fenced_worker' OR installation IS NULL THEN PERFORM {{tenantSchema}}.__P___error('forbidden'); END IF;
    n:=least({{tenantSchema}}.__P___int(a,'limit',10,1),100); result:='[]';
    stale:=to_char((moment-make_interval(secs=>COALESCE((ctx#>>'{settings,redeliver_after_s}')::integer,30))) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"');
    FOR rec IN SELECT r.id,r.doc FROM {{tenantSchema}}.__P___records r
      WHERE r.tenant_id=t AND r.kind='message' AND EXISTS(SELECT 1 FROM {{tenantSchema}}.__P___records i WHERE i.tenant_id=t AND i.kind='identity' AND i.id=r.doc->>'recipient_did' AND i.doc->>'installation_id'=installation AND i.doc->'active'='true'::jsonb)
      AND (r.doc->>'status'='queued' AND r.doc->>'available_at'<=stamp OR r.doc->>'status'='claimed' AND r.doc->>'claimed_at'<=stale)
      ORDER BY r.ordinal FOR UPDATE OF r SKIP LOCKED LOOP
      IF (rec.doc->>'attempts')::bigint>=maximum THEN
        PERFORM {{tenantSchema}}.__P___put(t,'message',rec.id,rec.doc||jsonb_build_object('status','dead','reason','max_delivery_attempts','acked_at',stamp));
        CONTINUE;
      END IF;
      IF jsonb_array_length(result)>=n THEN EXIT; END IF;
      row:=rec.doc||jsonb_build_object('status','claimed','claimed_at',stamp,'attempts',(rec.doc->>'attempts')::bigint+1,'admission_key','msg:'||rec.id);
      PERFORM {{tenantSchema}}.__P___put(t,'message',rec.id,row);
      result:=result||jsonb_build_array(jsonb_build_object('message_id',rec.id,'envelope',row->'envelope','attempts',row->'attempts'));
    END LOOP;
    RETURN jsonb_build_object('messages',result);
  ELSIF op IN ('message.ack','message.release') THEN
    ident:={{tenantSchema}}.__P___text(a,'message_id');
    SELECT doc INTO row FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='message' AND id=ident FOR UPDATE;
    IF row IS NULL THEN PERFORM {{tenantSchema}}.__P___error('unknown_message'); END IF;
    item:={{tenantSchema}}.__P___get(t,'identity',row->>'recipient_did');
    IF ctx->>'callerKind'<>'fenced_worker' OR item->>'installation_id' IS DISTINCT FROM installation OR item->'active' IS DISTINCT FROM 'true'::jsonb THEN PERFORM {{tenantSchema}}.__P___error('not_your_message'); END IF;
    IF op='message.ack' THEN
      IF a->>'outcome' IS NULL OR a->>'outcome' NOT IN ('processed','rejected') THEN PERFORM {{tenantSchema}}.__P___error('invalid_argument'); END IF;
      IF row->>'status' NOT IN ('processed','rejected','dead') THEN
        row:=row||jsonb_build_object('status',a->'outcome','reason',a->'reason','run_id',COALESCE(NULLIF(a->'run_id','null'),row->'run_id'),'acked_at',stamp);
      END IF;
    ELSE
      delay_s:={{tenantSchema}}.__P___int(a,'delay_s',0);
      IF row->>'status'='claimed' THEN
        IF (row->>'attempts')::bigint>=maximum THEN row:=row||jsonb_build_object('status','dead','reason','max_delivery_attempts','acked_at',stamp);
        ELSE row:=row||jsonb_build_object('status','queued','available_at',to_char((moment+make_interval(secs=>delay_s)) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"')); END IF;
      END IF;
    END IF;
    PERFORM {{tenantSchema}}.__P___put(t,'message',ident,row); RETURN '{}';
  ELSIF op='conversation.read' THEN
    ident:={{tenantSchema}}.__P___text(a,'conversation_id');
    SELECT COALESCE(jsonb_agg(doc-'conversation_id'-'claimed_at'-'available_at'-'admission_key' ORDER BY ordinal),'[]') INTO result
      FROM {{tenantSchema}}.__P___records WHERE tenant_id=t AND kind='message' AND doc->>'conversation_id'=ident;
    RETURN jsonb_build_object('messages',result);
  END IF;
  PERFORM {{tenantSchema}}.__P___error('unknown_export');
END $$;
"""
