export type Subject = { disciplineId: string; icon: string; title: string; completed: string; progress: number; tone: 'coral' | 'mint' | 'lavender' };

export const subjects: Subject[] = [
  { disciplineId: 'anatomy', icon: '🫀', title: 'Анатомия', completed: '8 из 12 тем', progress: 68, tone: 'coral' },
  { disciplineId: 'physiology', icon: '🧬', title: 'Физиология', completed: '5 из 10 тем', progress: 48, tone: 'mint' },
  { disciplineId: 'neuro', icon: '🧠', title: 'Неврология', completed: '3 из 8 тем', progress: 35, tone: 'lavender' },
];

export const weeklyActivity = [34, 57, 82, 46, 66, 38, 25];
