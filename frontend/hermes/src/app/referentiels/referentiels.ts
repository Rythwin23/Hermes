import { AgGridAngular } from 'ag-grid-angular';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { ChangeDetectorRef, Component, OnInit, inject } from '@angular/core';
import {
  AllCommunityModule,
  type ColDef,
  type GridApi,
  type GridReadyEvent,
  type RowClickedEvent,
  iconSetQuartzBold,
  themeQuartz,
} from 'ag-grid-community';
import { catchError, finalize, of, Subject, takeUntil, timeout } from 'rxjs';
import { unpack } from 'msgpackr';

interface ApiResponse {
  results: Record<string, unknown>[];
}

@Component({
  selector: 'app-referentiels',
  imports: [AgGridAngular, CommonModule],
  templateUrl: './referentiels.html',
  styleUrl: './referentiels.css',
})
export class Referentiels implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly changeDetector = inject(ChangeDetectorRef);
  private readonly apiUrl = '/api';
  private gridApi?: GridApi;
  private requestVersion = 0;
  private detailDestroy$ = new Subject<void>();

  selectedTable = 'stops';
  totalRowsByTable: Record<string, number> = {};
  isLoading = false;
  errorMessage = '';
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

  tables = [
    { key: 'stops', label: 'Stops' },
    { key: 'routes', label: 'Routes' },
  ];

  private readonly endpoints: Record<string, string> = {
    stops: '/stops',
    routes: '/routes',
  };

  selectedStop: Record<string, unknown> | null = null;
  stopChildren: Record<string, unknown>[] = [];
  stopRoutes: Record<string, unknown>[] = [];
  selectedRoute: Record<string, unknown> | null = null;
  routeStops: Record<string, unknown>[] = [];

  tableByKey: Record<string, { rowData: Record<string, unknown>[]; columnDefs: ColDef[] }> = {
    stops: {
      rowData: [],
      columnDefs: [
        { field: 'stop_id', headerName: 'Stop ID', minWidth: 220, sortable: true, filter: true },
        { field: 'stop_name', headerName: 'Nom', minWidth: 180, sortable: true, filter: true },
        {
          field: 'parent_stop_name',
          headerName: 'Nom Parent',
          minWidth: 180,
          sortable: true,
          filter: true,
        },
      ],
    },
    routes: {
      rowData: [],
      columnDefs: [
        { field: 'route_id', headerName: 'Route ID', minWidth: 220, sortable: true, filter: true },
        {
          field: 'route_long_name',
          headerName: 'Nom complet',
          minWidth: 180,
          sortable: true,
          filter: true,
        },
        {
          field: 'route_type_name',
          headerName: 'Type',
          width: 140,
          sortable: true,
          filter: 'agTextColumnFilter',
        },
        {
          field: 'route_color',
          headerName: 'Couleur',
          width: 120,
          sortable: true,
          filter: true,
          hide: true,
        },
      ],
    },
    // trips: {
    //   rowData: [],
    //   columnDefs: [
    //     { field: 'trip_id', headerName: 'Trip ID', minWidth: 180, sortable: true, filter: true },
    //     { field: 'route_id', headerName: 'Route ID', minWidth: 200, sortable: true, filter: true },
    //     {
    //       field: 'service_id',
    //       headerName: 'Service ID',
    //       minWidth: 150,
    //       sortable: true,
    //       filter: true,
    //     },
    //     {
    //       field: 'trip_headsign',
    //       headerName: 'Destination',
    //       minWidth: 180,
    //       sortable: true,
    //       filter: true,
    //     },
    //     { field: 'trip_short_name', headerName: 'Nom court', minWidth: 140, sortable: true },
    //     { field: 'direction_id', headerName: 'Direction', width: 120, sortable: true },
    //   ],
    // },
    // parent_child_stops: {
    //   rowData: [],
    //   columnDefs: [
    //     { field: 'parent_stop_id', headerName: 'Parent Stop ID', minWidth: 220, filter: true },
    //     { field: 'stop_name', headerName: 'Nom', minWidth: 180, filter: true },
    //     {
    //       field: 'child_stop_ids',
    //       headerName: 'Child Stop IDs',
    //       minWidth: 280,
    //       filter: true,
    //       cellDataType: false,
    //       valueFormatter: (params) => params.value?.join(', ') ?? '',
    //     },
    //     {
    //       field: 'child_stop_names',
    //       headerName: 'Child Stop Names',
    //       minWidth: 280,
    //       filter: true,
    //       cellDataType: false,
    //       valueFormatter: (params) => params.value?.join(', ') ?? '',
    //     },
    //   ],
    // },
    // parent_stop_routes: {
    //   rowData: [],
    //   columnDefs: [
    //     { field: 'parent_stop_id', headerName: 'Parent Stop ID', minWidth: 220, filter: true },
    //     { field: 'parent_stop_name', headerName: 'Nom', minWidth: 180, filter: true },
    //     {
    //       field: 'route_names',
    //       headerName: 'Routes',
    //       minWidth: 240,
    //       filter: true,
    //       cellDataType: false,
    //       valueFormatter: (params) => params.value?.join(', ') ?? '',
    //     },
    //     {
    //       field: 'routes_ids',
    //       headerName: 'Route IDs',
    //       minWidth: 280,
    //       filter: true,
    //       cellDataType: false,
    //       valueFormatter: (params) => params.value?.join(', ') ?? '',
    //     },
    //   ],
    // },
  };

  ngOnInit() {
    this.loadTable(this.selectedTable);
  }

  onGridReady(event: GridReadyEvent) {
    this.gridApi = event.api;
    this.gridApi.setGridOption('rowData', this.currentTable.rowData);
  }

  get currentTable() {
    return this.tableByKey[this.selectedTable];
  }

  setTable(tableKey: string) {
    this.selectedTable = tableKey;
    this.selectedStop = null;
    this.stopChildren = [];
    this.stopRoutes = [];
    this.selectedRoute = null;
    this.routeStops = [];
    this.loadTable(tableKey);
  }

  get totalRows() {
    return this.totalRowsByTable[this.selectedTable] ?? 0;
  }

  private loadTable(tableKey: string) {
    const endpoint = this.endpoints[tableKey];
    if (!endpoint) {
      return;
    }

    const requestVersion = ++this.requestVersion;
    this.isLoading = true;
    this.errorMessage = '';
    const table = this.tableByKey[tableKey];
    table.rowData = [];
    if (tableKey === this.selectedTable) {
      this.gridApi?.setGridOption('rowData', []);
    }

    this.http
      .get(`${this.apiUrl}${endpoint}`, {
        headers: new HttpHeaders({ Accept: 'application/msgpack' }),
        responseType: 'arraybuffer',
      })
      .pipe(
        timeout(120000),
        catchError((error: unknown) => {
          console.error('Erreur de chargement du référentiel', error);
          if (requestVersion === this.requestVersion) {
            this.errorMessage = "Impossible de récupérer les données depuis l'API.";
            table.rowData = [];
            this.changeDetector.detectChanges();
          }
          return of(null);
        }),
        finalize(() => {
          if (requestVersion === this.requestVersion) {
            this.isLoading = false;
            this.changeDetector.detectChanges();
          }
        }),
      )
      .subscribe((response) => {
        if (!response || requestVersion !== this.requestVersion) {
          return;
        }
        const decoded = unpack(new Uint8Array(response)) as ApiResponse;
        const rows = decoded.results ?? [];
        table.rowData = rows;
        if (tableKey === this.selectedTable) {
          this.gridApi?.setGridOption('rowData', rows);
        }
        this.totalRowsByTable[tableKey] = rows.length;
        this.changeDetector.detectChanges();
      });
  }

  onRowClicked(event: RowClickedEvent<Record<string, unknown>>) {
    const row = event.data;
    if (!row) {
      return;
    }

    this.detailDestroy$.next();

    if (this.selectedTable === 'stops') {
      const stopId = row['stop_id'];
      if (!stopId) {
        return;
      }

      this.selectedStop = row;
      this.selectedRoute = null;
      this.routeStops = [];
      this.loadStopDetail(String(stopId));
      return;
    }

    if (this.selectedTable === 'routes') {
      const routeId = row['route_id'];
      if (!routeId) {
        return;
      }

      this.selectedRoute = row;
      this.selectedStop = null;
      this.stopChildren = [];
      this.stopRoutes = [];
      this.loadRouteDetail(String(routeId));
    }
  }

  private loadStopDetail(stopId: string) {
    this.http
      .get(`${this.apiUrl}/stops/${stopId}`)
      .pipe(takeUntil(this.detailDestroy$))
      .subscribe((response: any) => {
        this.stopChildren = Array.isArray(response?.child_stops) ? response.child_stops : [];
        this.stopRoutes = Array.isArray(response?.routes) ? response.routes : [];
        this.changeDetector.detectChanges();
      });
  }

  private loadRouteDetail(routeId: string) {
    this.http
      .get(`${this.apiUrl}/routes/${routeId}`)
      .pipe(takeUntil(this.detailDestroy$))
      .subscribe((response: any) => {
        this.routeStops = Array.isArray(response?.stops) ? response.stops : [];
        this.changeDetector.detectChanges();
      });
  }

  get rowData() {
    return this.currentTable.rowData;
  }

  get columnDefs() {
    return this.currentTable.columnDefs;
  }

  getRowStyle = (params: { data?: Record<string, unknown> }) => {
    if (this.selectedTable !== 'routes') {
      return undefined;
    }

    const raw = params?.data?.['route_color'];
    const color = typeof raw === 'string' ? raw.trim() : '';
    if (!color) {
      return undefined;
    }

    const normalized = color.startsWith('#') ? color.slice(1) : color;
    const hex =
      normalized.length === 3
        ? normalized
            .split('')
            .map((char) => char + char)
            .join('')
        : normalized;
    if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
      return undefined;
    }

    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

    return {
      backgroundColor: `#${hex}`,
      color: luminance > 0.6 ? '#111827' : '#ffffff',
      borderColor: `#${hex}`,
    };
  };

  defaultColDef: ColDef = {
    resizable: true,
    sortable: true,
    filter: true,
    flex: 1,
    minWidth: 100,
  };
}
