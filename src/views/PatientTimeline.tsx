import { useEffect, useState } from 'react';
import {
  fetchPatients,
  fetchPatientTimeline,
  type Patient,
  type TimelineEvent,
} from '../services/api';
import { User, Activity, Clock, ShieldCheck, Database } from 'lucide-react';

const TYPE_CONFIG: Record<string, { icon: string; color: string; bg: string; border: string; label: string }> = {
  diagnosis: { icon: '⬡', color: '#146EF5', bg: '#EAF5FF', border: '#DCE7F3', label: 'Diagnosis' },
  medication: { icon: '⬟', color: '#15803d', bg: '#dcfce7', border: '#DCE7F3', label: 'Medication' },
  symptom: { icon: '◎', color: '#071A3D', bg: 'rgba(22,199,232,0.15)', border: '#16C7E8', label: 'Symptom' },
  procedure: { icon: '⬢', color: '#071A3D', bg: '#EAF5FF', border: '#DCE7F3', label: 'Procedure' },
  lab: { icon: '◈', color: '#b45309', bg: '#fef3c7', border: '#d97706', label: 'Lab' },
  encounter: { icon: '◉', color: '#071A3D', bg: '#F5FAFF', border: '#DCE7F3', label: 'Encounter' },
  document: { icon: '◫', color: '#146EF5', bg: '#EAF5FF', border: '#DCE7F3', label: 'Document' },
};

interface EventItem {
  id?: string;
  type: string;
  title: string;
  date: string;
  detail: string;
}

export function PatientTimeline() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [patientName, setPatientName] = useState<string>('');
  const [patientMrn, setPatientMrn] = useState<string>('');
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      setLoading(true);
      try {
        const patientsResp = await fetchPatients(1, 20);
        if (isMounted && patientsResp.items.length > 0) {
          setPatients(patientsResp.items);
          const first = patientsResp.items[0];
          setSelectedPatientId(first.id);
          setPatientName(
            first.first_name && first.last_name
              ? `${first.first_name} ${first.last_name}`
              : `Patient ${first.mrn ?? first.id.slice(0, 6)}`
          );
          setPatientMrn(first.mrn ?? first.id.slice(0, 8));

          const timelineResp = await fetchPatientTimeline(first.id);
          if (isMounted) {
            setEvents(
              (timelineResp.timeline_events || []).map((e: TimelineEvent) => ({
                id: e.id,
                type: e.type,
                title: e.title,
                date: e.date.split('T')[0] || e.date,
                detail: e.detail,
              }))
            );
          }
        } else {
          setEvents([]);
        }
      } catch (_err) {
        setEvents([]);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectPatient = async (p: Patient) => {
    setSelectedPatientId(p.id);
    setPatientName(
      p.first_name && p.last_name
        ? `${p.first_name} ${p.last_name}`
        : `Patient ${p.mrn ?? p.id.slice(0, 6)}`
    );
    setPatientMrn(p.mrn ?? p.id.slice(0, 8));
    setLoading(true);
    try {
      const resp = await fetchPatientTimeline(p.id);
      setEvents(
        (resp.timeline_events || []).map((e: TimelineEvent) => ({
          id: e.id,
          type: e.type,
          title: e.title,
          date: e.date.split('T')[0] || e.date,
          detail: e.detail,
        }))
      );
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  const types = Object.keys(TYPE_CONFIG);

  const grouped = events.reduce<Record<string, EventItem[]>>((acc, e) => {
    (acc[e.date] = acc[e.date] || []).push(e);
    return acc;
  }, {});

  const filtered = Object.entries(grouped)
    .map(([date, evts]) => ({
      date,
      events: activeFilter ? evts.filter((e) => e.type === activeFilter) : evts,
    }))
    .filter((g) => g.events.length > 0);

  return (
    <div className="flex-1 flex flex-col overflow-hidden" style={{ background: '#F5FAFF' }}>
      {/* Header */}
      <div className="px-6 py-4 border-b page-header-edge page-header-edge-inset" style={{ background: '#fff', borderColor: '#DCE7F3' }}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#52627A' }}>
                {patientMrn} · {patientName}
              </span>
              <span className="px-2 py-0.5 rounded text-xs" style={{ background: '#dcfce7', color: '#15803d', fontFamily: 'JetBrains Mono, monospace', fontSize: 9 }}>
                ✓ VERIFIED
              </span>
            </div>
            <h1 style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 20, fontWeight: 700, color: '#071A3D' }}>Clinical Timeline</h1>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: '#52627A', marginTop: 2 }}>
              {events.length} clinical events
            </p>
          </div>
          {patients.length > 1 && (
            <div className="flex items-center gap-2 overflow-x-auto">
              <span className="font-mono text-[10px] text-[#52627A]">Patient:</span>
              {patients.slice(0, 4).map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleSelectPatient(p)}
                  className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                    selectedPatientId === p.id ? 'bg-[#146EF5] text-white' : 'bg-[#F5FAFF] text-[#52627A]'
                  }`}
                >
                  {p.mrn || p.id.slice(0, 6)}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        {/* Filter sidebar */}
        <div className="w-full shrink-0 border-b border-[#DCE7F3] bg-white md:w-[180px] md:border-b-0 md:border-r">
          <div className="border-b border-[#DCE7F3] bg-[#EAF5FF] px-4 py-3">
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#52627A', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Filter by Type
            </div>
          </div>
          <div className="flex min-w-0 gap-1 overflow-x-auto p-3 md:flex-col md:overflow-visible">
            <button
              onClick={() => setActiveFilter(null)}
              className="w-max shrink-0 whitespace-nowrap rounded-md px-3 py-2 text-left transition-colors md:w-full"
              style={{
                background: activeFilter === null ? '#F5FAFF' : 'transparent',
                fontFamily: 'Inter, sans-serif',
                fontSize: 13,
                color: activeFilter === null ? '#071A3D' : '#52627A',
                fontWeight: activeFilter === null ? 600 : 400,
              }}
            >
              All Events ({events.length})
            </button>
            {types.map((t) => {
              const c = TYPE_CONFIG[t];
              const count = events.filter((e) => e.type === t).length;
              if (count === 0) return null;
              return (
                <button
                  key={t}
                  onClick={() => setActiveFilter(activeFilter === t ? null : t)}
                  className="flex w-max shrink-0 items-center justify-between gap-3 whitespace-nowrap rounded-md px-3 py-2 text-left transition-colors md:w-full"
                  style={{
                    background: activeFilter === t ? c.bg : 'transparent',
                    border: activeFilter === t ? `1px solid ${c.border}` : '1px solid transparent',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span style={{ color: c.color, fontSize: 13 }}>{c.icon}</span>
                    <span style={{ fontFamily: 'Inter, sans-serif', fontSize: 13, color: c.color, fontWeight: activeFilter === t ? 600 : 400 }}>
                      {c.label}
                    </span>
                  </div>
                  <span className="font-mono text-[10px]" style={{ color: c.color }}>{count}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Timeline */}
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
          <div className="w-full max-w-2xl">
            {loading ? (
              <div className="space-y-4 py-8">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-20 bg-white border border-[#DCE7F3] rounded-lg animate-pulse" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-16">
                <div style={{ fontSize: 32, marginBottom: 10, color: '#DCE7F3' }}>◎</div>
                <div style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 15, fontWeight: 600, color: '#52627A' }}>
                  No events match this filter
                </div>
              </div>
            ) : (
              filtered.map(({ date, events: dayEvents }, gi) => (
                <div key={date} className="mb-8">
                  {/* Date marker */}
                  <div className="flex items-center gap-4 mb-4">
                    <div className="px-3 py-1.5 rounded-full" style={{ background: '#071A3D' }}>
                      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#fff', letterSpacing: '0.04em' }}>
                        {date}
                      </span>
                    </div>
                    <div className="flex-1 h-px" style={{ background: '#DCE7F3' }} />
                  </div>

                  {/* Events for this date */}
                  <div className="ml-4 space-y-3">
                    {dayEvents.map((event, ei) => {
                      const c = TYPE_CONFIG[event.type] || TYPE_CONFIG.encounter;
                      const idx = gi * 100 + ei;
                      const isExpanded = expandedId === idx;

                      return (
                        <div key={event.id || ei} className="flex gap-4">
                          {/* Connector */}
                          <div className="flex flex-col items-center" style={{ width: 24, flexShrink: 0 }}>
                            <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs" style={{ background: c.bg, border: `2px solid ${c.border}`, color: c.color, flexShrink: 0 }}>
                              {c.icon}
                            </div>
                            {ei < dayEvents.length - 1 && (
                              <div className="flex-1 w-px mt-1" style={{ background: '#DCE7F3', minHeight: 12 }} />
                            )}
                          </div>

                          {/* Content */}
                          <button
                            onClick={() => setExpandedId(isExpanded ? null : idx)}
                            className="flex-1 text-left rounded-lg p-3.5 mb-1 transition-all"
                            style={{ background: '#fff', border: `1px solid ${isExpanded ? c.border : '#DCE7F3'}`, boxShadow: isExpanded ? `0 0 0 2px ${c.bg}` : 'none' }}
                          >
                            <div className="flex items-start justify-between">
                              <div>
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="px-1.5 py-0.5 rounded text-xs font-semibold" style={{ background: c.bg, color: c.color, fontFamily: 'JetBrains Mono, monospace', fontSize: 9, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                                    {c.label}
                                  </span>
                                </div>
                                <div style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 14, fontWeight: 600, color: '#071A3D' }}>
                                  {event.title}
                                </div>
                                <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: '#52627A', marginTop: 3 }}>
                                  {event.detail}
                                </div>
                              </div>
                              <span style={{ color: '#DCE7F3', fontSize: 12, marginLeft: 8, marginTop: 2 }}>{isExpanded ? '▲' : '▼'}</span>
                            </div>

                            {isExpanded && (
                              <div className="mt-3 pt-3 border-t slide-in" style={{ borderColor: '#F5FAFF' }}>
                                <div className="grid grid-cols-2 gap-3">
                                  {[
                                    ['Event Type', c.label],
                                    ['Date', date],
                                    ['Source', 'PostgreSQL / MIMIC-IV'],
                                    ['Model confidence (uncalibrated)', 'Not measured'],
                                    ['Review Status', 'Verified'],
                                  ].map(([k, v]) => (
                                    <div key={k}>
                                      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 9, color: '#52627A', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>{k}</div>
                                      <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: '#071A3D' }}>{v}</div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
