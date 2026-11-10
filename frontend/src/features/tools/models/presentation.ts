export interface PresentationSlide {
  id: string
  index: number
  image_url: string
  thumb_url: string | null
  updated_at: string
}

export interface Presentation {
  id: string
  title: string
  status: 'pending' | 'converting' | 'ready' | 'failed'
  created_at: string
  conversion_job_id: string | null
  slides: PresentationSlide[]
}
