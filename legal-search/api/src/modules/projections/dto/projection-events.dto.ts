import { Type } from 'class-transformer';
import {
  IsDateString,
  IsIn,
  IsInt,
  IsNotEmpty,
  IsOptional,
  IsString,
  Matches,
  Min,
  ValidateNested,
} from 'class-validator';

const DOC_ID_PATTERN = /^doc_[0-9a-hjkmnp-tv-z]{26}$/;
const PM_ID_PATTERN = /^pm_[0-9a-hjkmnp-tv-z]{26}$/;
const RUN_ID_PATTERN = /^run_[0-9a-hjkmnp-tv-z]{26}$/;
const SRC_ID_PATTERN = /^src_[0-9a-hjkmnp-tv-z]{26}$/;
const SV_ID_PATTERN = /^sv_[0-9a-hjkmnp-tv-z]{26}$/;
const AUTH_ID_PATTERN = /^auth_[a-z0-9_]+$/;

class ProvenanceDto {
  @IsString()
  @IsNotEmpty()
  tenant_id!: string;

  @IsString()
  @IsNotEmpty()
  corpus_id!: string;

  @IsString()
  @IsNotEmpty()
  scope_type!: string;

  @IsString()
  @Matches(SRC_ID_PATTERN)
  source_id!: string;

  @IsString()
  @Matches(SV_ID_PATTERN)
  source_version_id!: string;

  @IsString()
  @Matches(RUN_ID_PATTERN)
  run_id!: string;
}

class ProcessedPayloadDto {
  @IsString()
  @Matches(DOC_ID_PATTERN)
  document_id!: string;

  @IsInt()
  @Min(1)
  document_revision!: number;

  @IsString()
  @Matches(PM_ID_PATTERN)
  processing_manifest_id!: string;

  @IsString()
  @IsNotEmpty()
  processing_version!: string;

  @ValidateNested()
  @Type(() => ProvenanceDto)
  provenance!: ProvenanceDto;

  @IsOptional()
  @IsString()
  @Matches(AUTH_ID_PATTERN)
  authority_id?: string;

  @IsOptional()
  @IsString()
  @IsNotEmpty()
  authority_name?: string;

  @IsString()
  @IsIn(['active', 'superseded', 'repealed', 'withdrawn'])
  lifecycle_status!: 'active' | 'superseded' | 'repealed' | 'withdrawn';
}

class WithdrawnPayloadDto {
  @IsString()
  @Matches(DOC_ID_PATTERN)
  document_id!: string;

  @IsInt()
  @Min(1)
  document_revision!: number;

  @IsString()
  @Matches(PM_ID_PATTERN)
  processing_manifest_id!: string;

  @ValidateNested()
  @Type(() => ProvenanceDto)
  provenance!: ProvenanceDto;

  @IsString()
  @IsIn(['duplicate', 'invalid_source', 'rights_restricted', 'operator_withdrawn'])
  reason_code!: 'duplicate' | 'invalid_source' | 'rights_restricted' | 'operator_withdrawn';

  @IsOptional()
  @IsString()
  reason_summary?: string;

  @IsString()
  @IsIn(['remove', 'hide'])
  search_disposition!: 'remove' | 'hide';
}

export class DocumentProcessedEventDto {
  @IsString()
  @IsNotEmpty()
  event_id!: string;

  @IsString()
  @IsIn(['document.processed'])
  event_type!: 'document.processed';

  @IsInt()
  @Min(1)
  event_version!: number;

  @IsDateString()
  occurred_at!: string;

  @IsString()
  @IsIn(['document-intelligence'])
  producer!: 'document-intelligence';

  @IsOptional()
  @IsString()
  @Matches(RUN_ID_PATTERN)
  correlation_id?: string;

  @ValidateNested()
  @Type(() => ProcessedPayloadDto)
  payload!: ProcessedPayloadDto;
}

export class DocumentWithdrawnEventDto {
  @IsString()
  @IsNotEmpty()
  event_id!: string;

  @IsString()
  @IsIn(['document.withdrawn'])
  event_type!: 'document.withdrawn';

  @IsInt()
  @Min(1)
  event_version!: number;

  @IsDateString()
  occurred_at!: string;

  @IsString()
  @IsIn(['document-intelligence'])
  producer!: 'document-intelligence';

  @IsOptional()
  @IsString()
  @Matches(RUN_ID_PATTERN)
  correlation_id?: string;

  @ValidateNested()
  @Type(() => WithdrawnPayloadDto)
  payload!: WithdrawnPayloadDto;
}
