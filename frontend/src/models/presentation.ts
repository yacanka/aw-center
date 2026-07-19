export interface PresentationSlide {
  id: number
  image: string
}

export interface Presentation {
  id: number
  title: string
  status: string
  slides: PresentationSlide[]
}

export interface PresentationMutationResult {
  detail?: string
}
