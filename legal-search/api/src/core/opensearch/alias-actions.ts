/**
 * Alias action builders for the versioned-index cutover flow.
 *
 * Extracted from `scripts/opensearch-alias-cutover.ts` so the alias arithmetic is
 * typechecked and unit-tested: getting it wrong is how the read and write aliases end
 * up on *different* physical indices, which silently black-holes every projected
 * document (see docs/runbooks/projection-reindex-backfill.md, "read/write invariant").
 */

export type AliasAction = Record<string, unknown>;

/**
 * Move one alias off its previous targets and onto `destinationIndex`.
 *
 * Submitted as a single `_aliases` request, these actions apply atomically — there is no
 * window in which the alias resolves to nothing.
 */
export function moveAliasActions(
  alias: string,
  previousTargets: string[],
  destinationIndex: string,
  isWriteIndex = false,
): AliasAction[] {
  const actions: AliasAction[] = [];
  for (const indexName of previousTargets) {
    // Removing the alias from the index we're about to add it to would be self-defeating
    // (and OpenSearch applies actions in order), so a no-op move stays a no-op.
    if (indexName === destinationIndex) continue;
    actions.push({ remove: { index: indexName, alias } });
  }
  actions.push(
    isWriteIndex
      ? { add: { index: destinationIndex, alias, is_write_index: true } }
      : { add: { index: destinationIndex, alias } },
  );
  return actions;
}

/**
 * Point both the read and the write alias at `destinationIndex` in one atomic swap,
 * preserving the invariant that the two always resolve to the same physical index.
 */
export function cutoverAliasActions(
  readAlias: string,
  writeAlias: string,
  previousReadTargets: string[],
  previousWriteTargets: string[],
  destinationIndex: string,
): AliasAction[] {
  return [
    ...moveAliasActions(readAlias, previousReadTargets, destinationIndex),
    ...moveAliasActions(writeAlias, previousWriteTargets, destinationIndex, true),
  ];
}
