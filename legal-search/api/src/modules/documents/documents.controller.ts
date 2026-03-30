import { Controller, Get, Param } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import type { DocumentsService } from './documents.service';
import { DocumentDetailDto, SectionsResponseDto } from './dto/document-detail.dto';

/**
 * TODO: Wire a JWT AuthGuard once the auth provider is configured.
 * The @ApiBearerAuth decorator below is documentation-only and does NOT
 * enforce token validation at runtime.
 */
@ApiTags('documents')
@ApiBearerAuth()
@Controller('v1/documents')
export class DocumentsController {
  constructor(private readonly documentsService: DocumentsService) {}

  @Get(':document_id')
  @ApiOperation({ operationId: 'getDocument', summary: 'Get document detail' })
  @ApiResponse({ status: 200, description: 'Document found', type: DocumentDetailDto })
  @ApiResponse({ status: 404, description: 'Document not found' })
  async getDocument(@Param('document_id') documentId: string): Promise<DocumentDetailDto> {
    return this.documentsService.getById(documentId);
  }

  @Get(':document_id/sections')
  @ApiOperation({ operationId: 'getDocumentSections', summary: 'Get sections of a document' })
  @ApiResponse({ status: 200, description: 'Sections response', type: SectionsResponseDto })
  @ApiResponse({ status: 404, description: 'Document not found' })
  async getSections(@Param('document_id') documentId: string): Promise<SectionsResponseDto> {
    return this.documentsService.getSections(documentId);
  }
}
