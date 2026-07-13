import { describe, expect, it } from 'vitest';
import { type AliasAction, cutoverAliasActions, moveAliasActions } from './alias-actions';

const READ = 'evidara-documents-read-dev';
const WRITE = 'evidara-documents-write-dev';
const OLD = 'evidara-documents-read-dev-20260101000000';
const NEW = 'evidara-documents-read-dev-20260713000000';

describe('moveAliasActions', () => {
  it('removes the alias from every previous target and adds it to the destination', () => {
    expect(moveAliasActions(READ, [OLD], NEW)).toEqual([
      { remove: { index: OLD, alias: READ } },
      { add: { index: NEW, alias: READ } },
    ]);
  });

  it('marks the write alias as the write index so projections keep landing somewhere', () => {
    expect(moveAliasActions(WRITE, [OLD], NEW, true)).toEqual([
      { remove: { index: OLD, alias: WRITE } },
      { add: { index: NEW, alias: WRITE, is_write_index: true } },
    ]);
  });

  it('does not remove the alias from the index it is being added to', () => {
    expect(moveAliasActions(READ, [NEW], NEW)).toEqual([{ add: { index: NEW, alias: READ } }]);
  });

  it('creates the alias when it does not exist yet (fresh cluster)', () => {
    expect(moveAliasActions(READ, [], NEW)).toEqual([{ add: { index: NEW, alias: READ } }]);
  });
});

/** Every alias name an action list touches, whether adding or removing. */
function aliasesTouched(actions: AliasAction[]): string[] {
  const aliases = actions.flatMap((action) => {
    const entry = action as { add?: { alias: string }; remove?: { alias: string } };
    const alias = entry.add?.alias ?? entry.remove?.alias;
    return alias ? [alias] : [];
  });
  return [...new Set(aliases)].sort();
}

describe('cutoverAliasActions', () => {
  it('lands both aliases on the same physical index', () => {
    const actions = cutoverAliasActions(READ, WRITE, [OLD], [OLD], NEW);

    const added = actions.flatMap((action) => {
      const add = (action as { add?: { index: string; alias: string } }).add;
      return add ? [add] : [];
    });
    expect(added.map((a) => a.alias).sort()).toEqual([READ, WRITE]);
    expect(new Set(added.map((a) => a.index))).toEqual(new Set([NEW]));
  });

  it('staging the write alias alone leaves the read alias untouched', () => {
    // Phase 1 of a Delta-sourced reindex: writes go to the new index while reads keep
    // serving the old one, so the backfill is invisible to users until promotion.
    // (Substring checks would be wrong here — versioned index names embed the read alias.)
    const staged = moveAliasActions(WRITE, [OLD], NEW, true);
    expect(aliasesTouched(staged)).toEqual([WRITE]);
  });

  it('promoting the read alias alone leaves the write alias untouched', () => {
    const promoted = moveAliasActions(READ, [OLD], NEW);
    expect(aliasesTouched(promoted)).toEqual([READ]);
  });
});
