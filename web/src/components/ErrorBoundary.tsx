import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * 하위 컴포넌트가 렌더/이펙트에서 던진 에러를 잡아 fallback으로 대체한다.
 * 외부 위젯(YouTube iframe 등)이 죽어도 앱 전체가 흰 화면이 되지 않도록 하는 안전망.
 * key를 바꿔주면(예: 영상 ID) 다시 정상 상태로 복구된다.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    console.error('UI 컴포넌트 에러:', error)
  }

  render() {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}
