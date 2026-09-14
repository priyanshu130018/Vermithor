import { useQuery } from '@tanstack/react-query';
import { fetchRCAReports } from '../api/rca';

export function useRCA(groupKey?: string) {
  return useQuery({
    queryKey: ['rca', groupKey],
    queryFn: async () => {
      const res = await fetchRCAReports({ group_key: groupKey, page_size: 1 });
      return res.items[0] || null;
    },
    staleTime: 10000,
    retry: 1,
  });
}
