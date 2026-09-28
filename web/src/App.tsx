import { useEffect, useState } from "react";
import { type ContextInfo, getContexts, getHealth, type Health } from "./api";
import { ContextRoom, type Room } from "./components/ContextRoom";
import { Forum } from "./components/Forum";
import { type Settings, Welcome } from "./components/Welcome";

const SETTINGS_KEY = "agora.settings.v2";

function loadSettings(): Settings | null {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? (JSON.parse(raw) as Settings) : null;
  } catch {
    return null;
  }
}

function saveSettings(s: Settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* stockage indisponible : réglages valables jusqu'au rechargement */
  }
}

type Screen = { name: "welcome" } | { name: "forum" } | { name: "room"; id: string };

const EMPTY_ROOM: Room = { messages: [], logs: [] };

/** Tout est prêt quand l'index est là ; le modèle d'embeddings se charge sinon dans le serveur MCP. */
export const isReady = (h: Health | null) =>
  h !== null && h.index.status === "ready" && (h.embedder.status === "ready" || h.embedder.status === "error");

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(loadSettings);
  const [screen, setScreen] = useState<Screen>(settings ? { name: "forum" } : { name: "welcome" });
  const [contexts, setContexts] = useState<ContextInfo[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  // Une conversation par contexte : passer d'un guide à l'autre ne perd rien.
  const [rooms, setRooms] = useState<Record<string, Room>>({});

  useEffect(() => {
    let timer: number;
    const load = () =>
      getContexts()
        .then(setContexts)
        .catch(() => {
          timer = window.setTimeout(load, 2000); // le backend démarre encore
        });
    load();
    return () => clearTimeout(timer);
  }, []);

  // Premier lancement : on suit le téléchargement des archives et du modèle jusqu'à ce que tout soit prêt.
  useEffect(() => {
    let timer: number;
    let stopped = false;
    const poll = () =>
      getHealth()
        .then((h) => {
          if (stopped) return;
          setHealth(h);
          if (!isReady(h)) timer = window.setTimeout(poll, 1500);
        })
        .catch(() => {
          if (!stopped) timer = window.setTimeout(poll, 2000);
        });
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);

  // Les archives viennent d'arriver : les compteurs et l'étendue des contextes sont maintenant connus.
  const ready = isReady(health);
  useEffect(() => {
    if (ready)
      getContexts()
        .then(setContexts)
        .catch(() => undefined);
  }, [ready]);

  const current = screen.name === "room" ? contexts?.find((c) => c.id === screen.id) : undefined;
  useEffect(() => {
    document.title = current ? `${current.place} · Agora` : "Agora";
  }, [current]);

  if (!settings || screen.name === "welcome") {
    return (
      <Welcome
        initial={settings}
        onReady={(s) => {
          saveSettings(s);
          setSettings(s);
          setScreen({ name: "forum" });
        }}
      />
    );
  }

  if (screen.name === "room" && current && contexts) {
    return (
      <ContextRoom
        key={current.id}
        context={current}
        contexts={contexts}
        settings={settings}
        health={health}
        room={rooms[current.id] ?? EMPTY_ROOM}
        onRoom={(update) => setRooms((all) => ({ ...all, [current.id]: update(all[current.id] ?? EMPTY_ROOM) }))}
        onModel={(model) => {
          const next = { ...settings, model };
          saveSettings(next);
          setSettings(next);
        }}
        onSwitch={(id) => setScreen({ name: "room", id })}
        onLeave={() => setScreen({ name: "forum" })}
      />
    );
  }

  return (
    <Forum
      contexts={contexts}
      settings={settings}
      health={health}
      onEnter={(id) => setScreen({ name: "room", id })}
      onChangeModel={() => setScreen({ name: "welcome" })}
    />
  );
}
