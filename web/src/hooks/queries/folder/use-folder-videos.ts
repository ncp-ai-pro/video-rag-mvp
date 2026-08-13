import { useQuery } from "@tanstack/react-query";

import { fetchFolderVideos } from "@/api/folder";
import { isAnalysisActive, isMetadataPending, type FolderVideo } from "@/api/types";

const isSettling = (video: FolderVideo) =>
  isMetadataPending(video.analysis_status) || isAnalysisActive(video.analysis_status);

export function useFolderVideos(folderId: number | null) {
  return useQuery({
    queryKey: ["folder-videos", folderId],
    queryFn: () => fetchFolderVideos(folderId as number),
    enabled: folderId !== null,
    // metadata 수집·분석이 진행 중인 영상이 있으면 몇 초마다 다시 불러와 제목·상태가
    // 새로고침 없이 채워지게 한다. 다 끝나면(모두 succeeded/failed/metadata_only) 폴링을 멈춘다.
    refetchInterval: (query) => (query.state.data?.some(isSettling) ? 3000 : false),
  });
}
