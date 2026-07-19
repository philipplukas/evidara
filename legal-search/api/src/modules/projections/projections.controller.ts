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
  UseInterceptors,
} from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { PubSubUnwrapInterceptor } from '../../core/interceptors/pubsub-unwrap.interceptor';
// biome-ignore lint/style/useImportType: DTO classes are needed for runtime validation metadata.
import { DocumentProcessedEventDto, DocumentWithdrawnEventDto } from './dto/projection-events.dto';
import type { ProjectionHistoryStatus } from './projections.repository';
// biome-ignore lint/style/useImportType: Nest DI needs runtime class metadata.
import { type ProjectionApplyResult, ProjectionsService } from './projections.service';

@ApiTags('projections')
// Base is `/v1/projections` so the projection *reads* (`/documents`) sit beside the
// event intake (`/events/...`) instead of being forced under an `events/` prefix they
// have nothing to do with. Every existing route keeps its exact URL.
@Controller('/v1/projections')
@UseInterceptors(PubSubUnwrapInterceptor)
export class ProjectionsController {
  private readonly logger = new Logger(ProjectionsController.name);

  constructor(private readonly service: ProjectionsService) {}

  @Post('/events/document-processed')
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

  @Post('/events/document-withdrawn')
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

  /**
   * Enumerate the indexed documents, `document_id`-ordered and cursor-paged.
   *
   * This is the index side of the ADR-0005 reconcile diff. It lives here, behind the
   * projection repository, because `legal-search/api` owns every OpenSearch call
   * (ADR-0008); document-intelligence reads canonical Delta and asks this endpoint what
   * is derived, exactly as the Delta backfill already does in the other direction.
   */
  @Get('/documents')
  async listIndexedDocuments(
    @Query('after') after?: string,
    @Query('limit', new DefaultValuePipe(500), ParseIntPipe) limit?: number,
  ) {
    return this.service.listIndexedDocuments({ after, limit });
  }

  @Get('/events/history')
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

  @Get('/events/history/stats')
  async getHistoryStats() {
    return this.service.getHistoryStats();
  }
}
