import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronRight, ListVideo as ListVideoIcon, Loader2, PlayCircle } from "lucide-react";
import { toast } from "sonner";

import { ChatPanel } from "@/components/ChatPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { FolderVideos } from "@/components/FolderVideos";
import { Sidebar } from "@/components/Sidebar";
import type { PlayerHandle } from "@/components/Player";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useChat } from "@/hooks/chat/use-chat";
import { useIsMobile } from "@/hooks/use-mobile";
import { useMe } from "@/hooks/queries/workspace/use-me";
import { useFolders } from "@/hooks/queries/folder/use-folders";
import { useFolderVideos } from "@/hooks/queries/folder/use-folder-videos";
import { useAnalyzeVideo } from "@/hooks/mutations/video/use-analyze-video";
import { useWatchVideoAnalysis } from "@/hooks/analysis/use-watch-video-analysis";
import { isAnalysisActive, isMetadataPending, type FolderVideo } from "@/api/types";

/**
 * 화면 조립만 담당한다. 데이터 조회·SSE 동기화·서버 호출은 전부 훅으로 위임한다.
 * useChat을 여기서 만들어 ChatPanel·EvidencePanel이 같은 turns를 공유한다
 * (답변의 근거를 오른쪽 패널이 자동으로 동기화해서 보여주기 위함).
 *
 * 모바일과 데스크톱은 레이아웃이 완전히 다르다(아래 isMobile 분기 참고). CSS로만
 * 숨기면(예: hidden md:flex) FolderVideos·EvidencePanel이 두 군데 동시에 mount되어
 * YouTube Player가 playerRef를 두 번 잡으려 하는 문제가 생겨서, JS 조건 렌더링으로
 * 모바일/데스크톱 중 한쪽만 실제로 mount되게 한다.
 */

export default function WorkspacePage() {
  const { data: workspace } = useMe();
  const { data: folders } = useFolders();
  const isMobile = useIsMobile();

  // URL(?folder=)을 폴더 선택의 단일 진실 공급원으로 쓴다. 사이드바에서 폴더를
  // 바꿔도 여기로 반영되므로, 새로고침·링크 공유 어느 쪽에서도 마지막 폴더가 유지된다.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedFolderId = Number(searchParams.get("folder")) || null;

  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null);
  const playerRef = useRef<PlayerHandle>(null);

  // 모바일 전용: 영상 목록/재생+근거를 하단 시트로 뺐다(채팅을 메신저처럼 메인으로 쓰기 위함).
  const [listSheetOpen, setListSheetOpen] = useState(false);
  const [videoSheetOpen, setVideoSheetOpen] = useState(false);

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

  const handleSelectFolder = (folderId: number | null) => {
    if (folderId === null) {
      searchParams.delete("folder");
      setSearchParams(searchParams);
    } else {
      setSearchParams({ folder: String(folderId) });
    }
    setSelectedVideoId(null);
  };

  // 모바일에서 목록 시트로 영상을 고르면, 그 시트는 닫고 재생+근거 시트를 바로 연다
  // (목록 → 재생으로 이어지는 자연스러운 흐름).
  const handleSelectVideo = (video: FolderVideo) => {
    setSelectedVideoId(video.id);
    if (isMobile) {
      setListSheetOpen(false);
      setVideoSheetOpen(true);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedVideo) return;
    await analyzeVideoMutation.mutateAsync(selectedVideo.id);
  };

  const handleSeek = (youtubeId: string, seconds: number) => {
    playerRef.current?.playAt(youtubeId, seconds);
  };

  const videoLoading =
    !!selectedVideo &&
    (isAnalysisActive(selectedVideo.analysis_status) || isMetadataPending(selectedVideo.analysis_status));

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
          <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
            {selectedVideo?.title ?? "폴더와 영상을 선택하세요"}
          </span>
          {isMobile && (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="영상 목록"
              onClick={() => setListSheetOpen(true)}
            >
              <ListVideoIcon />
            </Button>
          )}
        </div>

        {/* 모바일 전용: 선택된 영상 요약 바. 탭하면 재생+근거 시트가 열린다. */}
        {isMobile && (
          <button
            type="button"
            onClick={() => setVideoSheetOpen(true)}
            disabled={!selectedVideo}
            className="flex shrink-0 items-center gap-2.5 border-b border-border/60 px-3 py-2 text-left disabled:opacity-60"
          >
            {selectedVideo ? (
              <>
                <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-primary/25 to-primary/5">
                  {videoLoading ? (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  ) : selectedVideo.thumbnail_url ? (
                    <img src={selectedVideo.thumbnail_url} alt="" className="size-full object-cover" />
                  ) : (
                    <PlayCircle className="size-4 text-primary" />
                  )}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">{selectedVideo.title}</span>
              </>
            ) : (
              <span className="flex-1 text-sm text-muted-foreground">영상 목록에서 영상을 선택하세요</span>
            )}
            <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
          </button>
        )}

        {isMobile ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <ChatPanel chat={chat} video={selectedVideo} onError={handleError} />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-row overflow-hidden">
            <section className="flex h-auto w-72 shrink-0 flex-col overflow-hidden border-r border-border/60">
              <FolderVideos
                selectedFolderId={selectedFolderId}
                selectedVideoId={selectedVideoId}
                onSelectVideo={handleSelectVideo}
                onError={handleError}
              />
            </section>

            <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <ChatPanel chat={chat} video={selectedVideo} onError={handleError} />
            </section>

            <section className="flex h-auto w-[340px] shrink-0 flex-col overflow-hidden border-l border-border/60">
              <EvidencePanel
                video={selectedVideo}
                playerRef={playerRef}
                onAnalyze={handleAnalyze}
                chat={chat}
                onSeek={handleSeek}
              />
            </section>
          </div>
        )}

        {isMobile && (
          <>
            <Sheet open={listSheetOpen} onOpenChange={setListSheetOpen}>
              {/* SheetContent 기본 닫기(X) 버튼이 top-3 right-3에 절대위치로 깔려서,
                  FolderVideos의 검색창+추가 버튼 줄과 겹쳤다. pt-10으로 그 아래로 내린다. */}
              <SheetContent side="bottom" className="h-[85vh] gap-0 px-0 pt-10 pb-0">
                <SheetHeader className="sr-only">
                  <SheetTitle>영상 목록</SheetTitle>
                </SheetHeader>
                <FolderVideos
                  selectedFolderId={selectedFolderId}
                  selectedVideoId={selectedVideoId}
                  onSelectVideo={handleSelectVideo}
                  onError={handleError}
                />
              </SheetContent>
            </Sheet>

            <Sheet open={videoSheetOpen} onOpenChange={setVideoSheetOpen}>
              <SheetContent side="bottom" className="h-[85vh] gap-0 overflow-y-auto px-0 pt-10 pb-0">
                <SheetHeader className="sr-only">
                  <SheetTitle>{selectedVideo?.title ?? "영상"}</SheetTitle>
                </SheetHeader>
                <EvidencePanel
                  video={selectedVideo}
                  playerRef={playerRef}
                  onAnalyze={handleAnalyze}
                  chat={chat}
                  onSeek={handleSeek}
                />
              </SheetContent>
            </Sheet>
          </>
        )}
      </SidebarInset>
    </SidebarProvider>
  );
}
