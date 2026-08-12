import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { ChatPanel } from "@/components/ChatPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { FolderVideos } from "@/components/FolderVideos";
import { Sidebar } from "@/components/Sidebar";
import type { PlayerHandle } from "@/components/Player";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useChat } from "@/hooks/chat/use-chat";
import { useMe } from "@/hooks/queries/workspace/use-me";
import { useFolders } from "@/hooks/queries/folder/use-folders";
import { useFolderVideos } from "@/hooks/queries/folder/use-folder-videos";
import { useAnalyzeVideo } from "@/hooks/mutations/video/use-analyze-video";
import { useWatchVideoAnalysis } from "@/hooks/analysis/use-watch-video-analysis";
import { isAnalysisActive, type FolderVideo } from "@/api/types";

/**
 * 화면 조립만 담당한다. 데이터 조회·SSE 동기화·서버 호출은 전부 훅으로 위임한다.
 * useChat을 여기서 만들어 ChatPanel·EvidencePanel이 같은 turns를 공유한다
 * (답변의 근거를 오른쪽 패널이 자동으로 동기화해서 보여주기 위함).
 */

export default function WorkspacePage() {
  const { data: workspace } = useMe();
  const { data: folders } = useFolders();

  // URL(?folder=)을 폴더 선택의 단일 진실 공급원으로 쓴다. 사이드바에서 폴더를
  // 바꿔도 여기로 반영되므로, 새로고침·링크 공유 어느 쪽에서도 마지막 폴더가 유지된다.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedFolderId = Number(searchParams.get("folder")) || null;

  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null);
  const playerRef = useRef<PlayerHandle>(null);

  // 폴더 목록이 도착했는데 URL에 폴더가 없으면(=홈에서 지정 없이 왔으면) 첫 폴더를 URL에 채운다.
  // replace를 써서 브라우저 뒤로가기 히스토리에 이 자동 선택 자체는 남기지 않는다.
  useEffect(() => {
    if (selectedFolderId === null && folders && folders.length > 0) {
      setSearchParams({ folder: String(folders[0].id) }, { replace: true });
    }
  }, [folders, selectedFolderId, setSearchParams]);

  const { data: videos = [] } = useFolderVideos(selectedFolderId);
  const selectedVideo =
    videos.find((video) => video.id === selectedVideoId) ?? null;

  const analyzeVideoMutation = useAnalyzeVideo(selectedFolderId, {
    onSuccess: () => toast.success("분석 작업을 등록했습니다."),
    onError: () => toast.error("분석 작업 등록에 실패했습니다."),
  });

  // 분석이 진행 중인 영상만 SSE를 연다. 캐시 반영은 훅 내부에서 처리된다.
  const watchedVideoId =
    selectedVideo && isAnalysisActive(selectedVideo.analysis_status)
      ? selectedVideo.id
      : null;
  useWatchVideoAnalysis(selectedFolderId, watchedVideoId);

  const handleError = (message: string) => toast.error(message);

  const chat = useChat(workspace?.workspace_code ?? null, selectedFolderId, selectedVideo?.id ?? null, handleError);

  const handleSelectFolder = (folderId: number) => {
    setSearchParams({ folder: String(folderId) });
    setSelectedVideoId(null);
  };

  const handleSelectVideo = (video: FolderVideo) => setSelectedVideoId(video.id);

  const handleAnalyze = async () => {
    if (!selectedVideo) return;
    await analyzeVideoMutation.mutateAsync(selectedVideo.id);
  };

  const handleSeek = (youtubeId: string, seconds: number) => {
    playerRef.current?.playAt(youtubeId, seconds);
  };

  return (
    // 사이드바는 shadcn Sidebar가 알아서 처리한다: 데스크톱은 아이콘 rail로 접었다 펴는 패널,
    // 모바일(<768px)은 오프캔버스 드로어. 여기선 그 옆 콘텐츠 영역만 신경 쓴다.
    <SidebarProvider className="min-h-0 flex-1">
      <Sidebar
        selectedFolderId={selectedFolderId}
        onSelectFolder={handleSelectFolder}
        onError={handleError}
      />

      <SidebarInset className="min-h-0">
        <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <span className="truncate text-sm text-muted-foreground">
            {selectedVideo?.title ?? "폴더와 영상을 선택하세요"}
          </span>
        </div>

        {/* 채팅이 메인이라 모바일에서 가장 먼저 오도록 order로 순서를 바꾼다.
            화면 높이에 고정하고 각 영역이 자체 스크롤한다(페이지 전체 스크롤 금지). */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
          <section className="order-2 flex h-[30vh] shrink-0 flex-col overflow-hidden border-t border-border/60 md:order-1 md:h-auto md:w-72 md:shrink-0 md:border-r md:border-t-0">
            <FolderVideos
              selectedFolderId={selectedFolderId}
              selectedVideoId={selectedVideoId}
              onSelectVideo={handleSelectVideo}
              onError={handleError}
            />
          </section>

          <section className="order-1 flex min-h-0 flex-1 flex-col overflow-hidden md:order-2">
            <ChatPanel chat={chat} videoTitle={selectedVideo?.title ?? null} onError={handleError} />
          </section>

          <section className="order-3 flex h-[34vh] shrink-0 flex-col overflow-hidden border-t border-border/60 md:h-auto md:w-[340px] md:shrink-0 md:border-l md:border-t-0">
            <EvidencePanel
              video={selectedVideo}
              playerRef={playerRef}
              onAnalyze={handleAnalyze}
              chat={chat}
              onSeek={handleSeek}
            />
          </section>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
