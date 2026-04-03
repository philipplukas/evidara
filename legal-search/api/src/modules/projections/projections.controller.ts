import { Body, Controller, HttpCode, HttpStatus, Post } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
// biome-ignore lint/style/useImportType: DTO classes are needed for runtime validation metadata.
import { DocumentProcessedEventDto, DocumentWithdrawnEventDto } from './dto/projection-events.dto';
// biome-ignore lint/style/useImportType: Nest DI needs runtime class metadata.
import { type ProjectionApplyResult, ProjectionsService } from './projections.service';

@ApiTags('projections')
@Controller('/v1/projections/events')
export class ProjectionsController {
  constructor(private readonly service: ProjectionsService) {}

  @Post('/document-processed')
  @HttpCode(HttpStatus.ACCEPTED)
  async receiveDocumentProcessed(
    @Body() event: DocumentProcessedEventDto,
  ): Promise<ProjectionApplyResult> {
    return this.service.applyDocumentProcessed(event);
  }

  @Post('/document-withdrawn')
  @HttpCode(HttpStatus.ACCEPTED)
  async receiveDocumentWithdrawn(
    @Body() event: DocumentWithdrawnEventDto,
  ): Promise<ProjectionApplyResult> {
    return this.service.applyDocumentWithdrawn(event);
  }
}
