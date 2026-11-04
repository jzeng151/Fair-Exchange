// Live mode (#116): sample producers the live chat can act as. They are real IDs from the sample producer
// records the agent reads (data/src/fx_data/producer_records.json); the place and crop are shown so a presenter
// can pick one. Local only: choosing a producer here stands in for sign-in (docs/specs/11-identity.md).
export interface LiveProducer { id: string; place: string; crop: string; flag: string }

export const liveProducers: LiveProducer[] = [
  { id: 'CFC19603C1B7B29C017954FD1DB2D620', place: 'Cauca, Colombia', crop: 'Coffee', flag: '🇨🇴' },
  { id: 'A7F700B04BCE55512CB026A71121426C', place: 'Cajamarca, Peru', crop: 'Coffee', flag: '🇵🇪' },
  { id: 'CED2DEE8ED99922FA5C6244DEF177AF3', place: 'La Paz, Honduras', crop: 'Coffee', flag: '🇭🇳' },
]
