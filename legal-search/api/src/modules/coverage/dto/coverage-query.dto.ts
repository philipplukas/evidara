import { Transform } from 'class-transformer';
import { IsInt, IsOptional, IsString, Matches, Max, Min } from 'class-validator';

/**
 * Query parameters for `GET /v1/coverage` (ADR-0042).
 *
 * `group_by` and `level` are validated in the service rather than by a decorator
 * so the rejection message can name the offending value. Both must REJECT an
 * unknown value, never ignore it: an ignored filter silently widens the scope,
 * and the caller reads the wider answer as the narrower one they asked for.
 */
export class CoverageQueryDto {
  @IsOptional()
  @IsString()
  group_by?: string;

  /** Comma-separated jurisdiction ids. Naming one is what makes its absence reportable. */
  @IsOptional()
  @IsString()
  jurisdiction_id?: string;

  @IsOptional()
  @IsString()
  authority_id?: string;

  @IsOptional()
  @IsString()
  document_type?: string;

  @IsOptional()
  @IsString()
  level?: string;

  /** ISO `YYYY-MM-DD`. Norms with unknown dates are kept, not dropped. */
  @IsOptional()
  @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'in_force_at must be an ISO date (YYYY-MM-DD)' })
  in_force_at?: string;

  @IsOptional()
  @Transform(({ value }) => (value === undefined ? undefined : Number(value)))
  @IsInt()
  @Min(1)
  @Max(1000)
  limit?: number;
}
