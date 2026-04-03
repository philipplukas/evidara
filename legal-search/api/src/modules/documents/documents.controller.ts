import { Controller, Get, Headers, Inject, Param, Query } from '@nestjs/common';
import { resolveLocale } from '../../core/i18n';
import { DocumentsService } from './documents.service';
// biome-ignore lint/style/useImportType: DTO class must be a value for ValidationPipe on @Query()
import { DocumentDetailQueryDto } from './dto/document-detail-query.dto';

@Controller('v1/documents')
export class DocumentsController {
  constructor(
    @Inject(DocumentsService)
    private readonly documentsService: DocumentsService,
  ) {}

  @Get(':document_id')
  async getDocument(
    @Param('document_id') id: string,
    @Query() query: DocumentDetailQueryDto,
    @Headers('accept-language') acceptLanguage?: string,
  ) {
    const locale = resolveLocale(acceptLanguage);
    return this.documentsService.getDetail(id, locale, query.processing_manifest_id);
  }

  @Get(':document_id/sections')
  async getSections(@Param('document_id') id: string) {
    const data = await this.documentsService.getSections(id);
    return { data };
  }
}
