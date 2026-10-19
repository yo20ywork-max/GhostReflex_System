"""Mechanical evidence checks for an explicit task contract.

This does not establish that a contract fully captures a natural-language request.
It is not connected to the production completion decision until that independent
semantic/coverage check and end-to-end acceptance have been validated.
"""
import hashlib,json

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def check_contract(request,contract,history,allowed_tools):
    """Return evidence satisfaction and witnesses, never an overall task success."""
    if not isinstance(request,str) or not request:raise ValueError('Original request required')
    if not isinstance(contract,dict) or set(contract)!={'request_sha256','requirements','before'}:raise ValueError('Invalid contract envelope')
    if contract['request_sha256']!=hashlib.sha256(request.encode()).hexdigest():raise ValueError('Contract belongs to another request')
    requirements=contract['requirements'];edges=contract['before']
    if not isinstance(requirements,list) or not 1<=len(requirements)<=128:raise ValueError('Bounded nonempty requirements required')
    if not isinstance(edges,list) or len(edges)>512:raise ValueError('Invalid ordering constraints')
    if not isinstance(history,list):raise ValueError('Ordered actual observations required')
    ids={};candidates={};failures=[];forbidden=[]
    for req in requirements:
        required={'id','source_quote','tool','args','mode','selection'}
        if not isinstance(req,dict) or not required<=set(req) or set(req)-required-{'output_equals','max_output_items','max_dispatches'}:raise ValueError('Invalid requirement fields')
        rid=req['id']
        if not isinstance(rid,str) or not rid or rid in ids:raise ValueError('Unique requirement identifiers required')
        quote=req['source_quote']
        if not isinstance(quote,str) or not quote.strip() or quote not in request:raise ValueError('Requirement lacks an exact source quote')
        if req['tool'] not in allowed_tools or not isinstance(req['args'],dict):raise ValueError('Unknown tool or invalid expected arguments')
        if req['mode'] not in ('require','forbid') or req['selection'] not in ('any','latest'):raise ValueError('Unknown observation policy')
        if 'max_output_items' in req and (type(req['max_output_items']) is not int or req['max_output_items']<0):raise ValueError('Invalid count bound')
        if 'max_dispatches' in req and (type(req['max_dispatches']) is not int or req['max_dispatches']<0):raise ValueError('Invalid dispatch bound')
        if req['mode']=='forbid' and ('output_equals' in req or 'max_output_items' in req):raise ValueError('A forbidden dispatch cannot depend on its response')
        ids[rid]=req
        matched=[]
        for index,item in enumerate(history,1):
            if not isinstance(item,dict):raise ValueError('Invalid observation')
            arguments=item.get('args')
            if item.get('tool')==req['tool'] and isinstance(arguments,dict) and all(k in arguments and fingerprint(arguments[k])==fingerprint(v) for k,v in req['args'].items()):matched.append((index,item))
        if req['mode']=='forbid':
            if matched:forbidden.append({'requirement':rid,'dispatch_sequences':[x[0] for x in matched]})
            continue
        if 'max_dispatches' in req and len(matched)>req['max_dispatches']:failures.append({'requirement':rid,'reason':'Observed dispatch count exceeds the explicit maximum.'})
        if req['selection']=='latest':matched=matched[-1:]
        valid=[]
        for index,item in matched:
            if item.get('ok') is not True or item.get('verified') is not True:continue
            if 'output_equals' in req and ('output' not in item or fingerprint(item['output'])!=fingerprint(req['output_equals'])):continue
            if 'max_output_items' in req:
                if not isinstance(item.get('output'),list) or len(item['output'])>req['max_output_items']:continue
            valid.append(index)
        candidates[rid]=valid
        if not valid:failures.append({'requirement':rid,'reason':'No matching verified observation satisfies this requirement.'})
    predecessors={rid:set() for rid in candidates};successors={rid:set() for rid in candidates}
    for edge in edges:
        if not isinstance(edge,dict) or set(edge)!={'first','then','source_quote'}:raise ValueError('Invalid order edge')
        first,then=edge['first'],edge['then'];quote=edge['source_quote']
        if first not in candidates or then not in candidates or first==then:raise ValueError('Order edge must refer to two required observations')
        if not isinstance(quote,str) or not quote.strip() or quote not in request:raise ValueError('Order constraint lacks source quote')
        predecessors[then].add(first);successors[first].add(then)
    # Earliest feasible witnesses in topological order satisfy all strict-before
    # constraints when such witnesses exist; this avoids combinatorial search.
    pending={rid:set(before) for rid,before in predecessors.items()};ready=sorted(rid for rid in pending if not pending[rid]);order=[]
    while ready:
        rid=ready.pop(0);order.append(rid)
        for after in sorted(successors[rid]):
            pending[after].discard(rid)
            if not pending[after]:ready.append(after)
    if len(order)!=len(candidates):raise ValueError('Cyclic ordering constraints')
    witnesses={}
    for rid in order:
        before=predecessors[rid]
        if any(x not in witnesses for x in before):continue
        threshold=max((witnesses[x] for x in before),default=0)
        possible=[x for x in candidates[rid] if x>threshold]
        if possible:witnesses[rid]=min(possible)
        elif candidates[rid]:failures.append({'requirement':rid,'reason':'Observed sequence violates an explicit ordering constraint.'})
    return {'evidence_satisfied':not forbidden and not failures and len(witnesses)==len(candidates),'witness_sequences':witnesses,'missing_or_mismatched':failures,'forbidden_dispatches':forbidden,'request_sha256':contract['request_sha256'],'contract_sha256':fingerprint(contract),'history_sha256':fingerprint(history),'contract_semantics_verified':False,'product_release_approved':False,'scope':'Mechanical checks only. Quoted text does not prove semantic accuracy or complete request coverage.'}
