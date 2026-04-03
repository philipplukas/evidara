import {
  Body,
  Controller,
  DefaultValuePipe,
  Get,
  HttpCode,
  HttpStatus,
  Logger,
  ParseIntPipe,
  Post,
  Query,
} from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
// biome-ignore lint/style/useImportType: DTO classes are needed for runtime validation metadata.
import { DocumentProcessedEventDto, DocumentWithdrawnEventDto } from './dto/projection-events.dto';
import type { ProjectionHistoryStatus } from './projections.repository';
// biome-ignore lint/style/useImportType: Nest DI needs runtime class metadata.
import { type ProjectionApplyResult, ProjectionsService } from './projections.service';

@ApiTags('projections')
@Controller('/v1/projections/events')
export class ProjectionsController {
  private readonly logger = new Logger(ProjectionsController.name);

  constructor(private readonly service: ProjectionsService) {}

  @Post('/document-processed')
  @HttpCode(HttpStatus.ACCEPTED)
  async receiveDocumentProcessed(
    @Body() event: DocumentProcessedEventDto,
  ): Promise<ProjectionApplyResult> {
    const ctx = {
      service: 'legal-search',
      event_type: event.event_type,
      event_id: event.event_id,
      correlation_id: event.correlation_id,
      document_id: event.payload?.document_id,
    };

    this.logger.log({ event: 'projection_event_received', ...ctx });
    const start = Date.now();

    try {
      const result = await this.service.applyDocumentProcessed(event);
      const duration_ms = Date.now() - start;

      if (result.status === 'applied') {
        this.logger.log({
          event: 'projection_applied',
          ...ctx,
          status: result.status,
          duration_ms,
        });
      } else {
        // stale or ignored_duplicate — not an error, but worth tracking
        this.logger.warn({
          event: 'projection_skipped',
          ...ctx,
          status: result.status,
          duration_ms,
        });
      }
      return result;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error({
        event: 'projection_apply_failed',
        ...ctx,
        error_class: 'transient',
        error_type: err.constructor.name,
        error_message: err.message,
        duration_ms: Date.now() - start,
      });
      throw error;
    }
  }

  @Post('/document-withdrawn')
  @HttpCode(HttpStatus.ACCEPTED)
  async receiveDocumentWithdrawn(
    @Body() event: DocumentWithdrawnEventDto,
  ): Promise<ProjectionApplyResult> {
    const ctx = {
      service: 'legal-search',
      event_type: event.event_type,
      event_id: event.event_id,
      correlation_id: event.correlation_id,
      document_id: event.payload?.document_id,
    };

    this.logger.log({ event: 'projection_event_received', ...ctx });
    const start = Date.now();

    try {
      const result = await this.service.applyDocumentWithdrawn(event);
      const duration_ms = Date.now() - start;

      if (result.status === 'applied') {
        this.logger.log({
          event: 'projection_applied',
          ...ctx,
          status: result.status,
          duration_ms,
        });
      } else {
        this.logger.warn({
          event: 'projection_skipped',
          ...ctx,
          status: result.status,
          duration_ms,
        });
      }
      return result;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error({
        event: 'projection_apply_failed',
        ...ctx,
        error_class: 'transient',
        error_type: err.constructor.name,
        error_message: err.message,
        duration_ms: Date.now() - start,
      });
      throw error;
    }
  }

  @Get('/history')
  async queryHistory(
    @Query('document_id') documentId?: string,
    @Query('run_id') runId?: string,
    @Query('status') status?: string,
    @Query('limit', new DefaultValuePipe(50), ParseIntPipe) limit?: number,
    @Query('offset', new DefaultValuePipe(0), ParseIntPipe) offset?: number,
  ) {
    return this.service.queryHistory({
      documentId,
      runId,
      status: status as ProjectionHistoryStatus | undefined,
      limit,
      offset,
    });
  }

  @Get('/history/stats')
  async getHistoryStats() {
    return this.service.getHistoryStats();
  }
}
