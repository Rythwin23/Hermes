import { AgGridAngular } from 'ag-grid-angular';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, inject } from '@angular/core';
import {
  AllCommunityModule,
  type ColDef,
  type GridApi,
  type GridReadyEvent,
  type RowClickedEvent,
  iconSetQuartzBold,
  themeQuartz,
} from 'ag-grid-community';
import { catchError, finalize, of, timeout } from 'rxjs';
import { ParentStopOption, StopsStore } from '../stops-store';

interface StopRef {
  stop_id: string;
  stop_name: string;
  station_id: string;
  station_name: string;
}

interface StopVisit extends StopRef {
  arrival_time: number;
  arrival_datetime: string;
  departure_time: number;
  departure_datetime: string;
}

interface TransferLeg {
  type: 'transfer';
  from: StopRef;
  to: StopRef;
  same_station: boolean;
  minimum_transfer_time: number;
}

interface TripLeg {
  type: 'trip';
  trip_id: string;
  route_id: string;
  route_name: string;
  route_color: string;
  trip_headsign: string;
  from: StopRef;
  to: StopRef;
  departure_time: number;
  departure_datetime: string;
  arrival_time: number;
  arrival_datetime: string;
  stops: StopVisit[];
}

type Leg = TransferLeg | TripLeg;

interface Journey {
  departure_datetime: string;
  arrival_datetime: string;
  duration_minutes: number;
  correspondence: number;
  legs: Leg[];
}

interface RaptorResponse {
  found: boolean;
  journeys: Journey[];
  error?: string;
}

interface JourneyRow {
  departure_stop_name: string;
  arrival_stop_name: string;
  departure_datetime: string;
  arrival_datetime: string;
  duration_minutes: number;
  correspondence: number;
  lines: string;
  journey: Journey;
}

@Component({
  selector: 'app-naviguer',
  imports: [AgGridAngular, CommonModule, FormsModule],
  templateUrl: './naviguer.html',
  styleUrl: './naviguer.css',
})
export class Naviguer {
  private readonly http = inject(HttpClient);
  private readonly changeDetector = inject(ChangeDetectorRef);
  readonly stopsStore = inject(StopsStore);
  private readonly apiUrl = '/api/raptor/test';
  private gridApi?: GridApi;

  fromStop = '';
  toStop = '';
  fromSuggestions: ParentStopOption[] = [];
  toSuggestions: ParentStopOption[] = [];
  // Initialize travelDate and departureTime with current date and time with correct GMT
  travelDate = new Date().toLocaleDateString().split('/').reverse().join('-');
  departureTime = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });

  isLoading = false;
  hasSearched = false;
  errorMessage = '';
  rowData: JourneyRow[] = [];
  selectedJourney: Journey | null = null;

  modules = [AllCommunityModule];
  myTheme = themeQuartz.withPart(iconSetQuartzBold).withParams({
    accentColor: '#176B5B',
    backgroundColor: '#FFFFFF',
    borderColor: '#DCE3DE',
    browserColorScheme: 'inherit',
    cellTextColor: '#1D2A28',
    columnBorder: false,
    fontFamily: ['Avenir Next', 'Trebuchet MS', 'sans-serif'],
    foregroundColor: '#1D2A28',
    headerBackgroundColor: '#EDF1ED',
  });

  columnDefs: ColDef<JourneyRow>[] = [
    {
      field: 'departure_stop_name',
      headerName: 'Départ',
      minWidth: 180,
      sortable: true,
      filter: true,
    },
    {
      field: 'arrival_stop_name',
      headerName: 'Arrivée',
      minWidth: 180,
      sortable: true,
      filter: true,
    },
    {
      field: 'duration_minutes',
      headerName: 'Durée (min)',
      width: 130,
      sortable: true,
      valueFormatter: (params) => `${params.value} min`,
    },
    {
      field: 'correspondence',
      headerName: 'Correspondances',
      width: 160,
      sortable: true,
    },
    { field: 'lines', headerName: 'Lignes', minWidth: 220, sortable: true, filter: true },
  ];

  defaultColDef: ColDef = {
    resizable: true,
    flex: 1,
    minWidth: 100,
  };

  onGridReady(event: GridReadyEvent) {
    this.gridApi = event.api;
  }

  updateStopSuggestions(field: 'from' | 'to') {
    const value = field === 'from' ? this.fromStop : this.toStop;
    const query = value.trim().toLocaleLowerCase();
    const suggestions =
      query.length < 2
        ? []
        : this.stopsStore
            .parentStops()
            .filter((stop) => stop.name.toLocaleLowerCase().includes(query))
            .slice(0, 8);

    if (field === 'from') {
      this.fromSuggestions = suggestions;
    } else {
      this.toSuggestions = suggestions;
    }
  }

  selectStop(field: 'from' | 'to', stop: ParentStopOption) {
    if (field === 'from') {
      this.fromStop = stop.name;
      this.fromSuggestions = [];
    } else {
      this.toStop = stop.name;
      this.toSuggestions = [];
    }
  }

  search() {
    if (!this.fromStop || !this.toStop || !this.travelDate || !this.departureTime) {
      this.errorMessage = 'Veuillez renseigner tous les champs de recherche.';
      return;
    }

    this.isLoading = true;
    this.hasSearched = true;
    this.errorMessage = '';
    this.selectedJourney = null;
    this.rowData = [];
    this.gridApi?.setGridOption('rowData', []);

    // get stop_id for the source and target stops based on their names
    const sourceStopId = this.stopsStore
      .parentStops()
      .find((stop) => stop.name === this.fromStop)?.id;
    const targetStopId = this.stopsStore
      .parentStops()
      .find((stop) => stop.name === this.toStop)?.id;
    const body = {
      source_stop_name: sourceStopId ?? this.fromStop,
      target_stop_name: targetStopId ?? this.toStop,
      stop_with_id: !!sourceStopId && !!targetStopId,
      departure_time: this.normalizeTime(this.departureTime),
      travel_date: this.travelDate,
    };

    this.http
      .post<RaptorResponse>(this.apiUrl, body)
      .pipe(
        timeout(120000),
        catchError((error: unknown) => {
          console.error("Erreur lors de la recherche d'itinéraire", error);
          this.errorMessage = "Impossible de récupérer les itinéraires depuis l'API.";
          return of(null);
        }),
        finalize(() => {
          this.isLoading = false;
          this.changeDetector.detectChanges();
        }),
      )
      .subscribe((response) => {
        if (!response) {
          return;
        }
        if (!response.found || response.journeys.length === 0) {
          this.errorMessage = response.error ?? 'Aucun itinéraire trouvé.';
          return;
        }
        this.rowData = response.journeys.map((journey) => this.toRow(journey));
        this.gridApi?.setGridOption('rowData', this.rowData);
      });
  }

  onRowClicked(event: RowClickedEvent<JourneyRow>) {
    this.selectedJourney = event.data?.journey ?? null;
  }

  legLines(journey: Journey): string {
    return journey.legs
      .filter((leg): leg is TripLeg => leg.type === 'trip')
      .map((leg) => leg.route_name)
      .join(' • ');
  }

  isTripLeg(leg: Leg): leg is TripLeg {
    return leg.type === 'trip';
  }

  isTransferLeg(leg: Leg): leg is TransferLeg {
    return leg.type === 'transfer';
  }

  formatTime(datetime: string): string {
    return datetime.slice(11, 16);
  }

  private toRow(journey: Journey): JourneyRow {
    const originStop = journey.legs[0]?.from;
    const destinationStop = journey.legs[journey.legs.length - 1]?.to;

    return {
      departure_stop_name: originStop?.station_name ?? originStop?.stop_name ?? '',
      arrival_stop_name: destinationStop?.station_name ?? destinationStop?.stop_name ?? '',
      departure_datetime: journey.departure_datetime ?? '',
      arrival_datetime: journey.arrival_datetime ?? '',
      duration_minutes: journey.duration_minutes ?? 0,
      correspondence: journey.correspondence ?? 0,
      lines: this.legLines(journey),
      journey,
    };
  }

  private normalizeTime(time: string): string {
    return time.length === 5 ? `${time}:00` : time;
  }
}
