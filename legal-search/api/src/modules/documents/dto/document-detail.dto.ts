import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class DocumentDetailDto {
  @ApiProperty() document_id!: string;
  @ApiProperty() title!: string;
  @ApiPropertyOptional() content?: string;
  @ApiPropertyOptional() jurisdiction?: string;
  @ApiPropertyOptional() document_type?: string;
  @ApiPropertyOptional({ format: 'date' }) effective_date?: string;
  @ApiPropertyOptional() source_id?: string;
  @ApiPropertyOptional({ format: 'date-time' }) processed_at?: string;
  @ApiPropertyOptional() sections_count?: number;
  @ApiPropertyOptional() citations_count?: number;
}

export class SectionSummaryDto {
  @ApiProperty() section_id!: string;
  @ApiPropertyOptional() title?: string;
  @ApiPropertyOptional() ordinal?: number;
  @ApiPropertyOptional() depth?: number;
  @ApiPropertyOptional({ description: 'First 200 characters of section content' })
  content_preview?: string;
}

export class SectionsResponseDto {
  @ApiProperty({ type: [SectionSummaryDto] }) data!: SectionSummaryDto[];
}
