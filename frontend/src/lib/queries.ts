import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { apiClient } from './api'
import type { PredictRequest, SimulateRequest } from './types'

export const queryKeys = {
  health: ['health'] as const,
  alerts: ['alerts'] as const,
  simulations: ['simulations'] as const,
  thresholdMetrics: (threshold: number) =>
    ['thresholdMetrics', threshold] as const,
}

function invalidateAlertBackedQueries(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.alerts })
}

function invalidateSimulationBackedQueries(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.simulations })
  invalidateAlertBackedQueries(queryClient)
}

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: apiClient.health,
  })
}

export function useAlertsQuery() {
  return useQuery({
    queryKey: queryKeys.alerts,
    queryFn: apiClient.getAlerts,
  })
}

export function useSimulationsQuery() {
  return useQuery({
    queryKey: queryKeys.simulations,
    queryFn: apiClient.getSimulations,
  })
}

export function useThresholdMetricsQuery(threshold: number) {
  return useQuery({
    queryKey: queryKeys.thresholdMetrics(threshold),
    queryFn: () => apiClient.getThresholdMetrics(threshold),
  })
}

export function usePredictMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: PredictRequest) => apiClient.predict(request),
    onSuccess: () => {
      invalidateAlertBackedQueries(queryClient)
    },
  })
}

export function usePredictRandomMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: apiClient.predictRandom,
    onSuccess: () => {
      invalidateAlertBackedQueries(queryClient)
    },
  })
}

export function useSimulationMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: SimulateRequest) => apiClient.simulate(request),
    onSuccess: () => {
      invalidateSimulationBackedQueries(queryClient)
    },
  })
}
