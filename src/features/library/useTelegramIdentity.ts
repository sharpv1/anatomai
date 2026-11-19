import {useSyncExternalStore} from 'react';
import type {TelegramPlatform} from '../../platform/telegram/TelegramPlatformAdapter';
import {telegramProfile} from './catalog';
export function useTelegramIdentity(platform:TelegramPlatform){const context=useSyncExternalStore(platform.subscribeBackButton,platform.getTelegramContextSnapshot,()=>false);return context?telegramProfile(window.Telegram?.WebApp):{name:null,photoUrl:null};}
