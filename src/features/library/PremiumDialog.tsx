import { useEffect, useRef } from 'react';
import type { TelegramPlatform } from '../../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../../platform/telegram/useTelegramBackButton';
export function PremiumDialog({platform,onClose}:{platform:TelegramPlatform;onClose:()=>void}){
 const ref=useRef<HTMLDialogElement>(null);
 useTelegramBackButton(platform,onClose);
 useEffect(()=>{const dialog=ref.current;dialog?.showModal();return()=>dialog?.close();},[]);
 return <dialog ref={ref} className="premium-dialog" aria-labelledby="premium-title" aria-describedby="premium-description" onCancel={e=>{e.preventDefault();onClose();}}><h2 id="premium-title">Premium скоро появится</h2><p id="premium-description">В будущем здесь появится информация о расширенном доступе ANATOMAI. Платежи и подписки пока не подключены. Покупка не выполняется.</p><button onClick={onClose} autoFocus>Понятно</button></dialog>;
}
