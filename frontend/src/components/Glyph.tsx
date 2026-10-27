import {
  Activity, Box, CheckCheck, ClipboardList, FileCheck2, FileText,
  FlaskConical, Radiation, ScanLine, Settings2, ShieldCheck,
  Tag, UsersRound, Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const mapping: Record<string, LucideIcon> = {
  file: FileText, shield: ShieldCheck, wrench: Wrench, settings: Settings2,
  blueprint: FileText, users: UsersRound, clipboard: ClipboardList,
  box: Box, scan: ScanLine, filecheck: FileCheck2,
  check: CheckCheck, flask: FlaskConical, radiation: Radiation,
  activity: Activity, tag: Tag,
};

export default function Glyph({ name, className = '' }: { name: string; className?: string }) {
  const Icon = mapping[name] ?? FileText;
  return <Icon size={19} strokeWidth={2} className={className} />;
}
