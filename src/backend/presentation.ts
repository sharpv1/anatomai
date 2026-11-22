import type { Discipline, User, Reference } from './contracts';
import type { ReviewQuestion } from '../features/tests/questionReview';
export function identity(user: User) {
    const name = [user.first_name, user.last_name].filter(Boolean).join(' ').replace(/[\u0000-\u001f\u007f]/g, ' ').trim() || (user.username ? `@${user.username}` : null);
    let photoUrl: string | null = null;
    try {
        if (user.photo_url) {
            const u = new URL(user.photo_url);
            if (u.protocol === 'https:' && !u.username && !u.password)
                photoUrl = u.href;
        }
    }
    catch { /* Initials fallback. */ }
    return { name, photoUrl };
}
export function subject(d: Discipline) { return { id: d.id, title: d.title, icon: ({ anatomy: '🫀', physiology: '🧬', neuro: '🧠', histology: '🔬' } as Record<string, string>)[d.icon_key] ?? '✚', color: ['blue', 'mint', 'violet', 'orange'].includes(d.color_token) ? d.color_token : 'blue', questionCount: d.question_count }; }
export function review(r: Reference): ReviewQuestion { return { id: r.question_id, text: r.text, answers: r.options.map(o => o.text), correctAnswer: r.correct_option_ids.map(id => r.options.findIndex(o => o.id === id)) }; }
