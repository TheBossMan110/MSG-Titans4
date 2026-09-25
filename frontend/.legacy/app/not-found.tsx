import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { Logo } from '@/components/supportnova'
export default function NotFound(){return <main className="page-empty"><Logo/><span className="eyebrow">404 / signal lost</span><h1 style={{fontSize:70,margin:0}}>That page drifted off course.</h1><p className="muted">The route you&apos;re looking for doesn&apos;t exist in this workspace.</p><Link href="/" className="button button-primary"><ArrowLeft size={16}/> Return home</Link></main>}
