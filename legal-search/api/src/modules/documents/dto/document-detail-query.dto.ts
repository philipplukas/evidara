import { IsOptional, IsString, Matches } from 'class-validator';

export class DocumentDetailQueryDto {
  @IsOptional()
  @IsString()
  @Matches(/^pm_[0-9a-hjkmnp-tv-z]{26}$/)
  processing_manifest_id?: string;
}
