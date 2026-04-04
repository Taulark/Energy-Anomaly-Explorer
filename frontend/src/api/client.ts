import axios from 'axios';

const API_BASE_URL = (import.meta.env?.VITE_API_URL as string) || '';

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface City {
  cities: string[];
}

export interface Building {
  buildings: string[];
}

export interface Year {
  years: number[];
}

export interface Status {
  status: string;
  message: string;
  ready: boolean;
}

export interface RunRequest {
  city: string;
  building: string;
  z_threshold: number;
  top_n: number;
  selected_year: string | null;
  feature_mode: string;
  top_k: number;
  include_cloud_type: boolean;
  enable_cost_estimate: boolean;
  electricity_rate: number;
  enable_insights: boolean;
  enable_recurrence: boolean;
  enable_cost_estimates: boolean;
  enable_ai_summary: boolean;
}

export interface AnomalyResult {
  anomaly_summary: {
    total_hours: number;
    anomaly_hours: number;
    anomaly_rate: number;
    avg_abs_z: number;
  };
  top_anomalies: any[];
  regression: any;
  insights: any;
  occupancy: any;
  cost: any;
  city?: string;
  building?: string;
  upload_info?: any;
  [key: string]: any;
}

export const api = {
  getCities: async (): Promise<string[]> => {
    const response = await client.get<City>('/api/cities');
    return response.data.cities;
  },

  prepareCity: async (city: string): Promise<Status> => {
    const response = await client.post<Status>('/api/prepare-city', { city });
    return response.data;
  },

  /** Fast: OpenEI CSV only. Full weather merge runs on first Run analysis. */
  ensureLoadProfile: async (city: string): Promise<Status> => {
    const response = await client.post<Status>('/api/ensure-load-profile', { city });
    return response.data;
  },

  getBuildings: async (city: string): Promise<string[]> => {
    const response = await client.get<Building>(`/api/buildings?city=${encodeURIComponent(city)}`);
    return response.data.buildings;
  },

  getYears: async (city: string, building: string): Promise<number[]> => {
    const response = await client.get<Year>(`/api/years?city=${encodeURIComponent(city)}&building=${encodeURIComponent(building)}`);
    return response.data.years;
  },

  runAnalysis: async (request: RunRequest): Promise<AnomalyResult> => {
    const response = await client.post<AnomalyResult>('/api/run', request, {
      timeout: 600_000,
    });
    return response.data;
  },

  uploadAndAnalyze: async (params: {
    file: File;
    locationName: string;
    latitude: number;
    longitude: number;
    timestampColumn: string;
    energyColumn: string;
    buildingName: string;
    zThreshold: number;
    topN: number;
    featureMode: string;
    topK: number;
    includeCloudType: boolean;
    electricityRate: number;
    enableInsights: boolean;
    enableRecurrence: boolean;
    enableCostEstimates: boolean;
  }): Promise<AnomalyResult> => {
    const formData = new FormData();
    formData.append('file', params.file);
    formData.append('location_name', params.locationName);
    formData.append('latitude', params.latitude.toString());
    formData.append('longitude', params.longitude.toString());
    formData.append('timestamp_column', params.timestampColumn);
    formData.append('energy_column', params.energyColumn);
    formData.append('building_name', params.buildingName);
    formData.append('z_threshold', params.zThreshold.toString());
    formData.append('top_n', params.topN.toString());
    formData.append('feature_mode', params.featureMode);
    formData.append('top_k', params.topK.toString());
    formData.append('include_cloud_type', params.includeCloudType.toString());
    formData.append('electricity_rate', params.electricityRate.toString());
    formData.append('enable_insights', params.enableInsights.toString());
    formData.append('enable_recurrence', params.enableRecurrence.toString());
    formData.append('enable_cost_estimates', params.enableCostEstimates.toString());

    const response = await client.post<AnomalyResult>('/api/upload-analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    });
    return response.data;
  },

  getUploadRequirements: async (): Promise<any> => {
    const response = await client.get('/api/upload-requirements');
    return response.data;
  },

  getForecast: async (city: string, building: string, forecastDays: number = 7): Promise<any> => {
    const response = await client.post('/api/forecast', {
      city,
      building,
      forecast_days: forecastDays,
    }, { timeout: 180000 });
    return response.data;
  },

  health: async (): Promise<any> => {
    const response = await client.get('/api/health');
    return response.data;
  },
};
