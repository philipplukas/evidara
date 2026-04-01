import { Controller, Get, Inject, Param } from '@nestjs/common';
import { DocumentsService } from './documents.service';

@Controller('v1/documents')
export class DocumentsController {
  constructor(
    @Inject(DocumentsService)
    private readonly documentsService: DocumentsService,
  ) {}

  @Get(':document_id')
  async getDocument(@Param('document_id') id: string) {
    return this.documentsService.getDetail(id);
  }

  @Get(':document_id/sections')
  async getSections(@Param('document_id') id: string) {
    const data = await this.documentsService.getSections(id);
    return { data };
  }
}
