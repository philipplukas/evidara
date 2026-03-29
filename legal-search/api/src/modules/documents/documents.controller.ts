import { Controller, Get, Param } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { DocumentsService } from './documents.service';
import { DocumentDetailDto, SectionsResponseDto } from './dto/document-detail.dto';

@ApiTags('documents')
@ApiBearerAuth()
@Controller('v1/documents')
export class DocumentsController {
  constructor(private readonly documentsService: DocumentsService) {}

  @Get(':document_id')
  @ApiOperation({ operationId: 'getDocument', summary: 'Get document detail' })
  async getDocument(@Param('document_id') documentId: string): Promise<DocumentDetailDto> {
    return this.documentsService.getById(documentId);
  }

  @Get(':document_id/sections')
  @ApiOperation({ operationId: 'getDocumentSections', summary: 'Get sections of a document' })
  async getSections(@Param('document_id') documentId: string): Promise<SectionsResponseDto> {
    return this.documentsService.getSections(documentId);
  }
}
