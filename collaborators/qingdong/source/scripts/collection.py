"""Compile retained-list collection using only the host's existing page DSL."""
from __future__ import annotations

import copy


def state_schema(channel):
    selectors = channel['selectors']
    return {'fields': {
        'url': {'source': 'page.url'},
        'route': {'source': 'page.url', 'transforms': [{'type': 'regex_capture', 'pattern': '^([^?#]+)', 'group': 1}]},
        'query': {'source': 'value', 'locator': {'any_css': selectors['keyword_inputs'], 'visible': True}},
        'filters': {'source': 'texts', 'locator': {'any_css': selectors['submitted_filter_chips']}},
        'page': {'source': 'text', 'locator': {'any_css': selectors['active_page']}},
    }}


def snapshot_step(channel, name='capture-list-state'):
    return {'id': name, 'op': 'page.extract', 'schema': state_schema(channel), 'save_as': 'search.list_state'}


def variable(path, value):
    return {'type': 'variable', 'path': path, 'operator': 'equals', 'value': value, 'case_sensitive': True}


def prepare_collection(steps, channel, card_schema, prior, restore_search=False):
    """Check the retained list; restore its query only on explicit request."""
    if not restore_search:
        steps[:] = [s for s in steps if s['action'] != 'page.navigate']
    search = next(s for s in steps if s['id'] == 'search-and-extract-cards')
    original = search['program']
    split = next(i for i, s in enumerate(original) if s['id'] == 'initialize-card-buffer')
    snapshot = prior.get('list_state')
    reusable = (isinstance(snapshot, dict) and isinstance(snapshot.get('url'), str)
                and '/search/getConditionItem' in snapshot['url']
                and isinstance(snapshot.get('query'), str)
                and isinstance(snapshot.get('filters'), list)
                and all(isinstance(x, str) for x in snapshot['filters'])
                # Liepin omits pagination for short result lists; null is an observed state.
                and 'page' in snapshot
                and (snapshot['page'] is None or isinstance(snapshot['page'], str)))
    # Match the search route, not tracking/query parameters in the URL. Tag order is immaterial.
    from urllib.parse import urlsplit
    url = urlsplit(snapshot['url']) if reusable else None
    filters = snapshot['filters'] if reusable else []
    same = {'all': [
        variable('search.list_state.route', url.scheme + '://' + url.netloc + url.path),
        variable('search.list_state.query', snapshot['query']),
        variable('search.list_state.page', snapshot['page']),
        variable('search.list_state.filters.length', len(filters)),
    ] + [{'type': 'variable', 'path': 'search.list_state.filters', 'operator': 'contains', 'value': v}
         for v in set(filters)]} if reusable else False
    ready = [
        {'id': 'restore-selected-cards', 'op': 'data.set', 'path': 'search.cards', 'value': prior['cards']},
        {'id': 'mark-collection-ready', 'op': 'data.set', 'path': 'search.collection_check',
         'value': {'status': 'ready'}},
    ]
    # A mismatch emits facts and zero candidates, rather than silently submitting an old query.
    search['program'] = [original[0]] + (original[1:split] if restore_search else []) + [
        snapshot_step(channel),
        {'id': 'initialize-unsupported-filter-buffer', 'op': 'data.set',
         'path': 'search.unsupported_filters', 'value': prior.get('unsupported_filters', [])},
        {'id': 'restore-card-pages', 'op': 'data.set', 'path': 'search.pages', 'value': prior.get('pages', [])},
        {'id': 'check-collection-state', 'op': 'flow.if',
         'condition': True if restore_search else same, 'then': ready,
         'else': [
             {'id': 'defer-selected-cards', 'op': 'data.set', 'path': 'search.cards', 'value': []},
             {'id': 'report-collection-mismatch', 'op': 'data.set', 'path': 'search.collection_check',
              'value': {'status': 'needs_restore', 'expected': snapshot, 'observed': {'$ref': 'search.list_state'}}},
         ]},
    ]
    search['return']['collection_check'] = {'$ref': 'search.collection_check'}
    detail = next(s for s in steps if s['id'] == 'collect-candidate-details')
    opening = detail['open']
    # Re-read stable identities just before every click; never reuse a stale row index.
    identity_schema = copy.deepcopy(card_schema)
    identity_schema['fields'] = {k: v for k, v in identity_schema['fields'].items()
                                 if k in ('source_candidate_id', 'candidate_ref', 'row_index')}
    opening['pre_program'] += [
        {'id': 'remember-selected-candidate', 'op': 'data.set', 'path': 'collect.wanted',
         'value': {'$item': 'candidate_ref'}},
        {'id': 'initialize-identity-matches', 'op': 'data.set', 'path': 'collect.matches', 'value': []},
        {'id': 'read-live-card-identities', 'op': 'page.extract_list', 'root': card_schema['root'],
         'schema': identity_schema, 'limit': 30, 'save_as': 'collect.live_cards'},
        {'id': 'locate-selected-candidate', 'op': 'flow.foreach', 'items': {'$ref': 'collect.live_cards'},
         'max_iterations': 30, 'program': [
             {'id': 'match-candidate-ref', 'op': 'flow.if',
              'condition': variable('collect.wanted', {'$item': 'candidate_ref'}),
              'then': [{'id': 'remember-live-row', 'op': 'data.append', 'path': 'collect.matches',
                        'value': {'$item': 'row_index'}, 'max_items': 30}], 'else': []}]},
        {'id': 'require-unique-selected-candidate', 'op': 'page.wait',
         'until': variable('collect.matches.length', 1), 'timeout_ms': 100},
    ]
    opening['target']['within']['index'] = {'$ref': 'collect.matches.0'}
    return steps
