import { Transform } from 'class-transformer';
import { IsInt, IsOptional, Matches, Max, Min } from 'class-validator';

export class NormHierarchyQueryDto {
  /**
   * ISO `YYYY-MM-DD`. Judges the hierarchy against the law in force on that
   * date — a ban enacted in 2019 is measured against 2019 law, not today's.
   */
  @IsOptional()
  @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'in_force_at must be an ISO date (YYYY-MM-DD)' })
  in_force_at?: string;

  /** Norms returned per level. */
  @IsOptional()
  @Transform(({ value }) => (value === undefined ? undefined : Number(value)))
  @IsInt()
  @Min(1)
  @Max(50)
  limit?: number;
}
