/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BaseHttpRequest } from './core/BaseHttpRequest';
import type { OpenAPIConfig } from './core/OpenAPI';
import { AxiosHttpRequest } from './core/AxiosHttpRequest';
import { AicssService } from './services/AicssService';
import { CloudProvidersService } from './services/CloudProvidersService';
import { ComposeService } from './services/ComposeService';
import { DefaultService } from './services/DefaultService';
import { LayersService } from './services/LayersService';
import { LlmServerService } from './services/LlmServerService';
import { ModelsService } from './services/ModelsService';
import { ProjectsService } from './services/ProjectsService';
import { ScriptMotionService } from './services/ScriptMotionService';
import { SettingsService } from './services/SettingsService';
import { V23DMeshExportService } from './services/V23DMeshExportService';
import { V2ComposeService } from './services/V2ComposeService';
import { V2ScriptMotionService } from './services/V2ScriptMotionService';
import { V2SequenceService } from './services/V2SequenceService';
import { V2ShotsService } from './services/V2ShotsService';
type HttpRequestConstructor = new (config: OpenAPIConfig) => BaseHttpRequest;
export class AicssClient {
  public readonly aicss: AicssService;
  public readonly cloudProviders: CloudProvidersService;
  public readonly compose: ComposeService;
  public readonly default: DefaultService;
  public readonly layers: LayersService;
  public readonly llmServer: LlmServerService;
  public readonly models: ModelsService;
  public readonly projects: ProjectsService;
  public readonly scriptMotion: ScriptMotionService;
  public readonly settings: SettingsService;
  public readonly v23DMeshExport: V23DMeshExportService;
  public readonly v2Compose: V2ComposeService;
  public readonly v2ScriptMotion: V2ScriptMotionService;
  public readonly v2Sequence: V2SequenceService;
  public readonly v2Shots: V2ShotsService;
  public readonly request: BaseHttpRequest;
  constructor(config?: Partial<OpenAPIConfig>, HttpRequest: HttpRequestConstructor = AxiosHttpRequest) {
    this.request = new HttpRequest({
      BASE: config?.BASE ?? '',
      VERSION: config?.VERSION ?? '0.1.0',
      WITH_CREDENTIALS: config?.WITH_CREDENTIALS ?? false,
      CREDENTIALS: config?.CREDENTIALS ?? 'include',
      TOKEN: config?.TOKEN,
      USERNAME: config?.USERNAME,
      PASSWORD: config?.PASSWORD,
      HEADERS: config?.HEADERS,
      ENCODE_PATH: config?.ENCODE_PATH,
    });
    this.aicss = new AicssService(this.request);
    this.cloudProviders = new CloudProvidersService(this.request);
    this.compose = new ComposeService(this.request);
    this.default = new DefaultService(this.request);
    this.layers = new LayersService(this.request);
    this.llmServer = new LlmServerService(this.request);
    this.models = new ModelsService(this.request);
    this.projects = new ProjectsService(this.request);
    this.scriptMotion = new ScriptMotionService(this.request);
    this.settings = new SettingsService(this.request);
    this.v23DMeshExport = new V23DMeshExportService(this.request);
    this.v2Compose = new V2ComposeService(this.request);
    this.v2ScriptMotion = new V2ScriptMotionService(this.request);
    this.v2Sequence = new V2SequenceService(this.request);
    this.v2Shots = new V2ShotsService(this.request);
  }
}

