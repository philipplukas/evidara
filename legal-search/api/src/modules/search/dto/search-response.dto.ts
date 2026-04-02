import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class SearchResultDto {
  @ApiProperty() document_id!: string;
  @ApiProperty() title!: string;
  @ApiPropertyOptional() snippet?: string;
  @ApiPropertyOptional() jurisdiction?: string;
  @ApiPropertyOptional() document_type?: string;
  @ApiPropertyOptional({ format: 'date' }) effective_date?: string;
  @ApiPropertyOptional() relevance_score?: number;
}

export class SearchResponseDto {
  @ApiProperty() query!: string;
  @ApiProperty() total_results!: number;
  @ApiProperty() page!: number;
  @ApiProperty() page_size!: number;
  @ApiProperty({ type: [SearchResultDto] }) results!: SearchResultDto[];
}
