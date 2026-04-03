import { Controller, Get, Headers, Inject, Param } from '@nestjs/common';
import { resolveLocale } from '../../core/i18n';
import { DocumentsService } from './documents.service';

@Controller('v1/documents')
export class DocumentsController {
  constructor(
    @Inject(DocumentsService)
    private readonly documentsService: DocumentsService,
  ) {}

  @Get(':document_id')
  async getDocument(
    @Param('document_id') id: string,
    @Headers('accept-language') acceptLanguage?: string,
    @Headers('x-correlation-id') correlationId?: string,
  ) {
    const locale = resolveLocale(acceptLanguage);
    return this.documentsService.getDetail(id, locale, correlationId);
  }

  @Get(':document_id/sections')
  async getSections(@Param('document_id') id: string) {
    const data = await this.documentsService.getSections(id);
    return { data };
  }
}
