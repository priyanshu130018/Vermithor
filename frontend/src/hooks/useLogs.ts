import { useMutation } from '@tanstack/react-query';
import { searchLogs } from '../api/logs';

export function useSearchLogs() {
  return useMutation({
    mutationFn: searchLogs,
  });
}
