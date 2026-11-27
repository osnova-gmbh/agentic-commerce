
CREATE TABLE {{tenantSchema}}.ac_deals_records (
  tenant_id uuid NOT NULL, kind text NOT NULL, id text NOT NULL,
  doc jsonb NOT NULL CHECK (jsonb_typeof(doc) = 'object'),
  ordinal bigint GENERATED ALWAYS AS IDENTITY,
  PRIMARY KEY (tenant_id, kind, id)
);
ALTER TABLE {{tenantSchema}}.ac_deals_records OWNER TO agentdb_owner;
REVOKE ALL ON {{tenantSchema}}.ac_deals_records FROM PUBLIC;

CREATE FUNCTION {{tenantSchema}}.ac_deals_error(code text) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN RAISE EXCEPTION USING ERRCODE = 'P0200', MESSAGE = code; END $$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_text(v jsonb, k text, optional boolean DEFAULT false)
RETURNS text LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF optional AND (NOT v ? k OR v->k = 'null'::jsonb) THEN RETURN NULL; END IF;
  IF jsonb_typeof(v->k) IS DISTINCT FROM 'string' OR length(v->>k)=0 THEN
    PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument');
  END IF;
  RETURN v->>k;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_int(v jsonb, k text, fallback bigint DEFAULT NULL, minimum bigint DEFAULT 0)
RETURNS bigint LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE n bigint;
BEGIN
  IF NOT v ? k OR v->k='null'::jsonb THEN n:=fallback;
  ELSIF jsonb_typeof(v->k)='number' AND (v->>k) ~ '^-?[0-9]+$' THEN n:=(v->>k)::bigint;
  ELSE PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  IF n IS NULL OR n<minimum THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  RETURN n;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_clean(v jsonb, rules jsonb, partial boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE result jsonb:='{}'; k text; r jsonb; item jsonb; typ text; valid boolean;
BEGIN
  IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(v) x WHERE NOT rules ? x) THEN
    PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument');
  END IF;
  FOR k,r IN SELECT key,value FROM jsonb_each(rules) LOOP
    IF partial AND NOT v ? k THEN CONTINUE; END IF;
    item:=v->k;
    IF item IS NULL OR item='null'::jsonb THEN
      IF COALESCE((r->>'required')::boolean,false) THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
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
    IF NOT valid THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
    result:=result||jsonb_build_object(k,item);
  END LOOP;
  RETURN result;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_get(t uuid, k text, ident text) RETURNS jsonb
LANGUAGE sql SET search_path = pg_catalog AS $$
  SELECT doc FROM {{tenantSchema}}.ac_deals_records WHERE tenant_id=t AND kind=k AND id=ident;
$$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_put(t uuid,k text,ident text,value jsonb) RETURNS void
LANGUAGE sql SET search_path = pg_catalog AS $$
  INSERT INTO {{tenantSchema}}.ac_deals_records(tenant_id,kind,id,doc) VALUES(t,k,ident,value)
  ON CONFLICT(tenant_id,kind,id) DO UPDATE SET doc=excluded.doc;
$$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_operator(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ctx->>'callerKind' IS DISTINCT FROM 'tenant_client'
     OR NULLIF(ctx#>>'{settings,operator_principal_id}','') IS NULL
     OR ctx->>'principalId' IS DISTINCT FROM ctx#>>'{settings,operator_principal_id}' THEN
    PERFORM {{tenantSchema}}.ac_deals_error('forbidden');
  END IF;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_escrow(ctx jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  IF ctx->>'callerKind' IS DISTINCT FROM 'fenced_worker'
     OR ctx->>'installationId' IS DISTINCT FROM ctx#>>'{settings,escrow_installation_id}' THEN
    PERFORM {{tenantSchema}}.ac_deals_error('forbidden');
  END IF;
END $$;

CREATE UNIQUE INDEX ac_deals_hash ON {{tenantSchema}}.ac_deals_records(tenant_id,(doc->>'hash')) WHERE kind='event';
CREATE UNIQUE INDEX ac_deals_source ON {{tenantSchema}}.ac_deals_records(tenant_id,(doc->>'source_message_id')) WHERE kind='event' AND doc->>'source_message_id' IS NOT NULL;
CREATE UNIQUE INDEX ac_deals_posting ON {{tenantSchema}}.ac_deals_records(tenant_id,(doc->>'source_id'),(doc->>'account')) WHERE kind='posting';
CREATE UNIQUE INDEX ac_deals_active_intent ON {{tenantSchema}}.ac_deals_records(tenant_id,(doc->>'deal_id'))
 WHERE kind='intent' AND doc->>'kind' IN ('payout','refund') AND doc->>'status' IN ('prepared','submitted','unknown');
CREATE INDEX ac_deals_by_deal ON {{tenantSchema}}.ac_deals_records(tenant_id,kind,(doc->>'deal_id'));

CREATE FUNCTION {{tenantSchema}}.ac_deals_row(t uuid,k text,deal text,item jsonb,merge boolean,stamp text) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE rules jsonb; keyname text; ident text; old jsonb; row jsonb; failure text;
BEGIN
  CASE k
    WHEN 'delivery' THEN rules:='{"delivery_id":{"type":"text","default":null,"required":true,"nullable":false},"artifact_id":{"type":"text","default":null,"required":true,"nullable":false},"sha256":{"type":"text","default":null,"required":true,"nullable":false},"media_type":{"type":"text","default":null,"required":true,"nullable":false},"delivered_at":{"type":"text","default":null,"required":true,"nullable":false},"attempt":{"type":"positive","default":null,"required":true,"nullable":false},"byte_length":{"type":"int","default":null,"required":true,"nullable":false},"status":{"type":"text","default":"delivered","required":false,"nullable":false}}'; keyname:='delivery_id'; failure:='invalid_argument';
    WHEN 'evaluation' THEN rules:='{"evaluation_request_id":{"type":"text","default":null,"required":true,"nullable":false},"delivery_id":{"type":"text","default":null,"required":true,"nullable":false},"evaluator_id":{"type":"text","default":null,"required":true,"nullable":false},"evaluator_did":{"type":"text","default":null,"required":true,"nullable":false},"respond_by":{"type":"text","default":null,"required":true,"nullable":false},"evaluator_version":{"type":"int","default":null,"required":true,"nullable":false},"resends":{"type":"int","default":0,"required":false,"nullable":false},"verdict_message_id":{"type":"text","default":null,"required":false,"nullable":true},"outcome":{"type":"text","default":null,"required":false,"nullable":true,"enum":["pass","fail","error"]}}'; keyname:='evaluation_request_id'; failure:='invalid_argument';
    WHEN 'intent' THEN rules:='{"intent_id":{"type":"text","default":null,"required":true,"nullable":false},"currency":{"type":"text","default":null,"required":true,"nullable":false},"to_iban":{"type":"text","default":null,"required":true,"nullable":false},"kind":{"type":"text","default":null,"required":true,"nullable":false,"enum":["payout","fee","refund","return_unmatched"]},"amount_minor":{"type":"int","default":null,"required":true,"nullable":false},"status":{"type":"text","default":"prepared","required":false,"nullable":false,"enum":["prepared","submitted","unknown","confirmed","failed"]},"bank_ref":{"type":"text","default":null,"required":false,"nullable":true}}'; keyname:='intent_id'; failure:='intent_conflict';
    WHEN 'credit' THEN rules:='{"bank_event_id":{"type":"text","default":null,"required":true,"nullable":false},"reference":{"type":"text","default":null,"required":true,"nullable":false},"from_iban":{"type":"text","default":null,"required":true,"nullable":false},"received_at":{"type":"text","default":null,"required":true,"nullable":false},"amount_minor":{"type":"int","default":null,"required":true,"nullable":false},"disposition":{"type":"text","default":null,"required":true,"nullable":false,"enum":["funded","returned"]}}'; keyname:='bank_event_id'; failure:='duplicate_credit';
    WHEN 'posting' THEN rules:='{"posting_id":{"type":"text","default":null,"required":true,"nullable":false},"source_id":{"type":"text","default":null,"required":true,"nullable":false},"account":{"type":"text","default":null,"required":true,"nullable":false,"enum":["held","seller","fee","buyer_refund","returned"]},"amount_minor":{"type":"signed","default":null,"required":true,"nullable":false}}'; keyname:='posting_id'; failure:='duplicate_posting';
    ELSE PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument');
  END CASE;
  IF item->>'deal_id' IS NOT NULL AND item->>'deal_id'<>deal THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  ident:={{tenantSchema}}.ac_deals_text(item,keyname);
  old:={{tenantSchema}}.ac_deals_get(t,k,ident);
  IF old IS NOT NULL AND NOT merge THEN PERFORM {{tenantSchema}}.ac_deals_error(failure); END IF;
  IF old IS NOT NULL AND old->>'deal_id'<>deal THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  row:={{tenantSchema}}.ac_deals_clean(item-'deal_id',rules,old IS NOT NULL);
  row:=COALESCE(old,'{}')||row||jsonb_build_object('deal_id',deal);
  IF k='evaluation' AND NOT EXISTS(SELECT 1 FROM {{tenantSchema}}.ac_deals_records WHERE tenant_id=t AND kind='delivery' AND id=row->>'delivery_id' AND doc->>'deal_id'=deal) THEN
    PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument');
  END IF;
  IF k IN ('intent','posting') AND old IS NULL THEN row:=row||jsonb_build_object('created_at',stamp); END IF;
  IF k='intent' THEN row:=row||jsonb_build_object('updated_at',stamp); END IF;
  BEGIN
    IF merge THEN PERFORM {{tenantSchema}}.ac_deals_put(t,k,ident,row);
    ELSE INSERT INTO {{tenantSchema}}.ac_deals_records(tenant_id,kind,id,doc) VALUES(t,k,ident,row); END IF;
  EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.ac_deals_error(failure);
  END;
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_commit(ctx jsonb,a jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; ident text; expected bigint; previous text; ev jsonb; fields jsonb;
  old jsonb; known jsonb; stamp text:=to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"');
  key text; item jsonb; array_name text; kind_name text; position bigint:=0; outbox_id text; row jsonb;
BEGIN
  PERFORM {{tenantSchema}}.ac_deals_escrow(ctx);
  IF EXISTS(SELECT 1 FROM jsonb_object_keys(a) k WHERE k NOT IN ('deal_id','expected_seq','expected_hash','event','deal','outbox','deliveries','evaluations','intents','credits','postings')) THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  ident:={{tenantSchema}}.ac_deals_text(a,'deal_id'); expected:={{tenantSchema}}.ac_deals_int(a,'expected_seq'); previous:={{tenantSchema}}.ac_deals_text(a,'expected_hash');
  ev:=a->'event'; fields:=COALESCE(NULLIF(a->'deal','null'),'{}');
  IF jsonb_typeof(ev) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(ev) k WHERE k NOT IN ('deal_id','seq','prev_hash','hash','event_type','actor_did','body','state_after','source_message_id'))
    OR ev->>'deal_id' IS NOT NULL AND ev->>'deal_id'<>ident THEN PERFORM {{tenantSchema}}.ac_deals_error('bad_event'); END IF;
  IF jsonb_typeof(fields)<>'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(fields) k WHERE k NOT IN ('deal_id','buyer_org_id','seller_org_id','offer_id','terms','terms_hash')) THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  FOREACH key IN ARRAY ARRAY['prev_hash','hash','event_type','actor_did','state_after'] LOOP
    IF jsonb_typeof(ev->key) IS DISTINCT FROM 'string' OR length(ev->>key)=0 THEN PERFORM {{tenantSchema}}.ac_deals_error('bad_event'); END IF;
  END LOOP;
  IF ev->>'hash' !~ '^[0-9a-f]{64}$' OR ev->>'prev_hash' !~ '^[0-9a-f]{64}$'
    OR jsonb_typeof(ev->'body') IS DISTINCT FROM 'object' OR jsonb_typeof(ev->'seq') IS DISTINCT FROM 'number'
    OR ev->>'seq' !~ '^[1-9][0-9]*$' THEN PERFORM {{tenantSchema}}.ac_deals_error('bad_event'); END IF;
  IF ev->'source_message_id' IS NOT NULL AND ev->'source_message_id'<>'null'::jsonb AND
    (jsonb_typeof(ev->'source_message_id')<>'string' OR ev->>'source_message_id'='') THEN PERFORM {{tenantSchema}}.ac_deals_error('bad_event'); END IF;
  FOREACH key IN ARRAY ARRAY['buyer_org_id','seller_org_id','offer_id'] LOOP
    IF fields->key IS NOT NULL AND fields->key<>'null'::jsonb THEN PERFORM {{tenantSchema}}.ac_deals_text(fields,key); END IF;
  END LOOP;
  IF fields->'terms' IS NOT NULL AND fields->'terms'<>'null'::jsonb AND jsonb_typeof(fields->'terms')<>'object' THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  IF fields->>'terms_hash' IS NOT NULL AND fields->>'terms_hash' !~ '^[0-9a-f]{64}$' THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  FOREACH key IN ARRAY ARRAY['outbox','deliveries','evaluations','intents','credits','postings'] LOOP
    IF jsonb_typeof(COALESCE(NULLIF(a->key,'null'),'[]'))<>'array' THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  END LOOP;
  PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':deal:'||ident,0));
  IF ev->>'source_message_id' IS NOT NULL THEN
    SELECT doc INTO known FROM {{tenantSchema}}.ac_deals_records WHERE tenant_id=t AND kind='event' AND doc->>'source_message_id'=ev->>'source_message_id';
    IF known IS NOT NULL THEN
      IF known->>'deal_id'<>ident THEN PERFORM {{tenantSchema}}.ac_deals_error('bad_event'); END IF;
      RETURN jsonb_build_object('seq',known->'seq','hash',known->'hash','duplicate',true);
    END IF;
  END IF;
  old:={{tenantSchema}}.ac_deals_get(t,'deal',ident);
  IF expected<>COALESCE((old->>'head_seq')::bigint,0) OR previous<>COALESCE(old->>'head_hash',repeat('0',64)) THEN PERFORM {{tenantSchema}}.ac_deals_error('head_mismatch'); END IF;
  IF old IS NULL THEN
    FOREACH key IN ARRAY ARRAY['buyer_org_id','seller_org_id','offer_id'] LOOP
      IF fields->>key IS NULL THEN PERFORM {{tenantSchema}}.ac_deals_error('head_mismatch'); END IF;
    END LOOP;
    old:=jsonb_build_object('deal_id',ident,'buyer_org_id',fields->'buyer_org_id','seller_org_id',fields->'seller_org_id','offer_id',fields->'offer_id','created_at',stamp,'terms',NULL,'terms_hash',NULL);
  ELSE
    FOREACH key IN ARRAY ARRAY['buyer_org_id','seller_org_id','offer_id'] LOOP
      IF fields->>key IS NOT NULL AND fields->key<>old->key THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
    END LOOP;
  END IF;
  IF (ev->>'seq')::bigint<>expected+1 OR ev->>'prev_hash'<>previous THEN PERFORM {{tenantSchema}}.ac_deals_error('bad_event'); END IF;
  row:=old||jsonb_build_object('state',ev->'state_after','head_seq',ev->'seq','head_hash',ev->'hash','updated_at',stamp);
  FOREACH key IN ARRAY ARRAY['terms','terms_hash'] LOOP
    IF fields->key IS NOT NULL AND fields->key<>'null'::jsonb THEN row:=row||jsonb_build_object(key,fields->key); END IF;
  END LOOP;
  PERFORM {{tenantSchema}}.ac_deals_put(t,'deal',ident,row);
  BEGIN
    INSERT INTO {{tenantSchema}}.ac_deals_records(tenant_id,kind,id,doc)
      VALUES(t,'event',jsonb_build_array(ident,ev->'seq')::text,ev||jsonb_build_object('deal_id',ident,'source_message_id',ev->'source_message_id','recorded_at',stamp));
  EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.ac_deals_error('bad_event'); END;
  FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(NULLIF(a->'outbox','null'),'[]')) LOOP
    IF jsonb_typeof(item)<>'object' OR item-'deal_id'-'outbox_id'-'envelope'<>'{}' OR jsonb_typeof(item->'envelope') IS DISTINCT FROM 'object' OR item->>'deal_id' IS NOT NULL AND item->>'deal_id'<>ident THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
    outbox_id:={{tenantSchema}}.ac_deals_text(item,'outbox_id');
    BEGIN
      INSERT INTO {{tenantSchema}}.ac_deals_records(tenant_id,kind,id,doc) VALUES(t,'outbox',outbox_id,
        jsonb_build_object('outbox_id',outbox_id,'deal_id',ident,'seq',ev->'seq','envelope',item->'envelope','status','pending','sent_at',NULL,'created_at',stamp,'ordinal',position));
    EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END;
    position:=position+1;
  END LOOP;
  FOR array_name,kind_name IN SELECT * FROM (VALUES('deliveries','delivery'),('evaluations','evaluation'),('intents','intent'),('credits','credit'),('postings','posting')) AS kinds(a,b) LOOP
    FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(NULLIF(a->array_name,'null'),'[]')) LOOP
      PERFORM {{tenantSchema}}.ac_deals_row(t,kind_name,ident,item,kind_name IN ('delivery','evaluation'),stamp);
    END LOOP;
  END LOOP;
  RETURN jsonb_build_object('seq',ev->'seq','hash',ev->'hash','duplicate',false);
END $$;

CREATE FUNCTION {{tenantSchema}}.ac_deals_dispatch(ctx jsonb,a jsonb,op text) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE t uuid:=(ctx->>'tenantId')::uuid; ident text; row jsonb; item jsonb; result jsonb; n bigint;
  stamp text:=to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'); key text; kind_name text;
BEGIN
  IF jsonb_typeof(a) IS DISTINCT FROM 'object' THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
  IF op='deal.commit' THEN RETURN {{tenantSchema}}.ac_deals_commit(ctx,a);
  ELSIF op IN ('outbox.mark_sent','intent.update') THEN
    PERFORM {{tenantSchema}}.ac_deals_escrow(ctx);
    IF op='outbox.mark_sent' THEN
      ident:={{tenantSchema}}.ac_deals_text(a,'outbox_id');
      UPDATE {{tenantSchema}}.ac_deals_records SET doc=doc||jsonb_build_object('status','sent','sent_at',stamp) WHERE tenant_id=t AND kind='outbox' AND id=ident AND doc->>'status'='pending';
    ELSE
      ident:={{tenantSchema}}.ac_deals_text(a,'intent_id');
      PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':intent:'||ident,0));
      row:={{tenantSchema}}.ac_deals_get(t,'intent',ident);
      IF row IS NULL THEN PERFORM {{tenantSchema}}.ac_deals_error('unknown_intent'); END IF;
      IF a->>'status' IS NULL OR a->>'status' NOT IN ('prepared','submitted','unknown','confirmed','failed') THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
      row:=row||jsonb_build_object('status',a->'status','updated_at',stamp);
      IF a->>'bank_ref' IS NOT NULL THEN row:=row||jsonb_build_object('bank_ref',{{tenantSchema}}.ac_deals_text(a,'bank_ref')); END IF;
      BEGIN PERFORM {{tenantSchema}}.ac_deals_put(t,'intent',ident,row);
      EXCEPTION WHEN unique_violation THEN PERFORM {{tenantSchema}}.ac_deals_error('intent_conflict'); END;
      IF jsonb_typeof(COALESCE(NULLIF(a->'postings','null'),'[]'))<>'array' THEN PERFORM {{tenantSchema}}.ac_deals_error('invalid_argument'); END IF;
      FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(NULLIF(a->'postings','null'),'[]')) LOOP
        item:=jsonb_build_object('source_id',ident)||item;
        PERFORM {{tenantSchema}}.ac_deals_clean(item-'deal_id','{"posting_id":{"type":"text","default":null,"required":true,"nullable":false},"source_id":{"type":"text","default":null,"required":true,"nullable":false},"account":{"type":"text","default":null,"required":true,"nullable":false,"enum":["held","seller","fee","buyer_refund","returned"]},"amount_minor":{"type":"signed","default":null,"required":true,"nullable":false}}'::jsonb,true);
        IF NOT EXISTS(SELECT 1 FROM {{tenantSchema}}.ac_deals_records WHERE tenant_id=t AND kind='posting' AND doc->>'source_id'=item->>'source_id' AND doc->>'account'=item->>'account') THEN
          PERFORM {{tenantSchema}}.ac_deals_row(t,'posting',row->>'deal_id',item,false,stamp);
        END IF;
      END LOOP;
    END IF;
    RETURN '{}';
  ELSIF op='outbox.pending' THEN
    n:={{tenantSchema}}.ac_deals_int(a,'limit',50);
    SELECT COALESCE(jsonb_agg(x.doc ORDER BY x.created,x.deal,x.seq,x.position,x.id),'[]') INTO result FROM (
      SELECT doc-'status'-'sent_at'-'created_at'-'ordinal' AS doc,doc->>'created_at' created,doc->>'deal_id' deal,(doc->>'seq')::bigint seq,(doc->>'ordinal')::bigint position,id
      FROM {{tenantSchema}}.ac_deals_records WHERE tenant_id=t AND kind='outbox' AND doc->>'status'='pending'
      ORDER BY created,deal,seq,position,id LIMIT n) x;
    RETURN jsonb_build_object('entries',result);
  ELSIF op='deal.list' THEN
    SELECT COALESCE(jsonb_agg(jsonb_build_object('deal_id',doc->'deal_id','state',doc->'state','buyer_org_id',doc->'buyer_org_id','seller_org_id',doc->'seller_org_id','offer_id',doc->'offer_id','head_seq',doc->'head_seq','price_minor',doc#>'{terms,price_minor}','currency',doc#>'{terms,currency}','created_at',doc->'created_at','updated_at',doc->'updated_at') ORDER BY doc->>'created_at' DESC,doc->>'updated_at' DESC,id),'[]')
      INTO result FROM {{tenantSchema}}.ac_deals_records WHERE tenant_id=t AND kind='deal';
    RETURN jsonb_build_object('deals',result);
  ELSIF op='deal.read' THEN
    ident:={{tenantSchema}}.ac_deals_text(a,'deal_id');
    result:=jsonb_build_object('deal',{{tenantSchema}}.ac_deals_get(t,'deal',ident));
    FOR key,kind_name IN SELECT * FROM (VALUES('events','event'),('deliveries','delivery'),('evaluations','evaluation'),('intents','intent'),('credits','credit')) AS kinds(a,b) LOOP
      SELECT COALESCE(jsonb_agg(CASE kind_name WHEN 'evaluation' THEN r.doc-'deal_id' ELSE r.doc END ORDER BY
        CASE kind_name WHEN 'event' THEN (r.doc->>'seq')::bigint WHEN 'delivery' THEN (r.doc->>'attempt')::bigint WHEN 'evaluation' THEN ({{tenantSchema}}.ac_deals_get(t,'delivery',r.doc->>'delivery_id')->>'attempt')::bigint END,
        CASE kind_name WHEN 'intent' THEN r.doc->>'created_at' WHEN 'credit' THEN r.doc->>'received_at' ELSE r.doc->>'delivery_id' END,r.id),'[]')
        INTO item FROM {{tenantSchema}}.ac_deals_records r WHERE tenant_id=t AND kind=kind_name AND doc->>'deal_id'=ident;
      result:=result||jsonb_build_object(key,item);
    END LOOP;
    RETURN result;
  ELSIF op='ledger.balances' THEN
    ident:={{tenantSchema}}.ac_deals_text(a,'deal_id',true); result:='{}';
    FOREACH key IN ARRAY ARRAY['held','seller','fee','buyer_refund','returned'] LOOP
      SELECT COALESCE(sum((doc->>'amount_minor')::bigint),0) INTO n FROM {{tenantSchema}}.ac_deals_records WHERE tenant_id=t AND kind='posting' AND doc->>'account'=key AND (ident IS NULL OR doc->>'deal_id'=ident);
      result:=result||jsonb_build_object(key,n);
    END LOOP;
    RETURN result;
  END IF;
  PERFORM {{tenantSchema}}.ac_deals_error('unknown_export');
END $$;

ALTER FUNCTION {{tenantSchema}}.ac_deals_error(text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_error(text) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_text(jsonb,text,boolean) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_text(jsonb,text,boolean) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_int(jsonb,text,bigint,bigint) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_int(jsonb,text,bigint,bigint) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_clean(jsonb,jsonb,boolean) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_clean(jsonb,jsonb,boolean) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_get(uuid,text,text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_get(uuid,text,text) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_put(uuid,text,text,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_put(uuid,text,text,jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_operator(jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_operator(jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_escrow(jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_escrow(jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_row(uuid,text,text,jsonb,boolean,text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_row(uuid,text,text,jsonb,boolean,text) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_commit(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_commit(jsonb,jsonb) FROM PUBLIC;

ALTER FUNCTION {{tenantSchema}}.ac_deals_dispatch(jsonb,jsonb,text) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{tenantSchema}}.ac_deals_dispatch(jsonb,jsonb,text) FROM PUBLIC;
