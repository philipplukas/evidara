/**
 * Which jurisdictions does the corpus actually hold? (#986)
 *
 * The index **is** the corpus, so a `jurisdiction_ids` terms aggregation over
 * the read alias is the truthful answer — not a seed, not a config list, not
 * the coverage ledger's *expectations*. It is cached for
 * `HOLDINGS_TTL_MS`: the answer changes only when a processing run lands, and a
 * per-request aggregation would put a second round trip on the hot path.
 *
 * ## Three states, not two
 *
 * `held` / `not held` is not the whole vocabulary. This service can also fail
 * to find out, and that third state is what keeps the refusal honest:
 *
 *   - a non-empty set  -> usable evidence; anything not in it is not held
 *   - an EMPTY set     -> reported as `unknown`, never as "holds nothing"
 *   - a failure        -> `unknown`
 *
 * The empty case matters because of #675: when the live index has drifted, an
 * aggregation over a missing field returns **empty buckets rather than an
 * error**. Treating empty as "the corpus holds no jurisdiction at all" would
 * turn a mapping defect into a refusal of every jurisdictional query — a false
 * refusal the caller cannot detect. So absence of evidence is never evidence of
 * absence here, and callers get `undefined`.
 */
import { Inject, Injectable, Logger } from '@nestjs/common';
import { SEARCH_REPOSITORY, type SearchRepository } from './search.repository';

/** How long a holdings snapshot is reused. A run landing is the only thing that changes it. */
export const HOLDINGS_TTL_MS = 5 * 60 * 1000;

@Injectable()
export class CorpusJurisdictionsService {
  private readonly logger = new Logger(CorpusJurisdictionsService.name);
  private cached?: { ids: Set<string>; at: number };
  private inFlight?: Promise<Set<string> | undefined>;

  constructor(
    @Inject(SEARCH_REPOSITORY)
    private readonly repository: SearchRepository,
  ) {}

  /**
   * The canonical jurisdiction ids the index holds at least one document for,
   * or `undefined` when that could not be established. `undefined` must never
   * be read as "holds nothing".
   */
  async heldJurisdictionIds(now: number = Date.now()): Promise<Set<string> | undefined> {
    if (this.cached && now - this.cached.at < HOLDINGS_TTL_MS) return this.cached.ids;
    // Collapse a thundering herd after expiry onto one aggregation.
    if (this.inFlight) return this.inFlight;

    this.inFlight = this.load(now).finally(() => {
      this.inFlight = undefined;
    });
    return this.inFlight;
  }

  private async load(now: number): Promise<Set<string> | undefined> {
    try {
      const ids = await this.repository.getHeldJurisdictionIds();
      if (ids.length === 0) {
        // Empty buckets are indistinguishable from a drifted mapping (#675).
        this.logger.warn(
          'jurisdiction_ids aggregation returned no buckets; corpus holdings treated as UNKNOWN, ' +
            'so no query will be refused on coverage grounds. If this persists, check the index ' +
            'mapping (`npm run mapping:check-drift`).',
        );
        return undefined;
      }
      const set = new Set(ids);
      this.cached = { ids: set, at: now };
      return set;
    } catch (err) {
      // A refusal built on a failed lookup would be a lie. Degrade to "unknown".
      this.logger.warn(
        `could not establish corpus jurisdiction holdings: ${
          err instanceof Error ? err.message : String(err)
        }`,
      );
      return undefined;
    }
  }
}
