import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { catchError, finalize, of, timeout } from 'rxjs';
import { unpack } from 'msgpackr';

interface StopsResponse {
  results: StopRecord[];
}

interface StopRecord {
  stop_id: string;
  stop_name: string;
  parent_stop_name?: string | null;
}

export interface ParentStopOption {
  id: string;
  name: string;
}

@Injectable({ providedIn: 'root' })
export class StopsStore {
  private readonly http = inject(HttpClient);
  private hasLoaded = false;
  private isLoading = false;

  readonly parentStops = signal<ParentStopOption[]>([]);
  readonly loading = signal(false);
  readonly error = signal('');

  load(): void {
    if (this.hasLoaded || this.isLoading) {
      return;
    }

    this.isLoading = true;
    this.loading.set(true);
    this.error.set('');

    this.http
      .get('/api/stops', {
        headers: new HttpHeaders({ Accept: 'application/msgpack' }),
        responseType: 'arraybuffer',
      })
      .pipe(
        timeout(120000),
        catchError((error: unknown) => {
          console.error('Erreur de chargement des arrêts', error);
          this.error.set("Impossible de récupérer les arrêts depuis l'API.");
          return of(null);
        }),
        finalize(() => {
          this.isLoading = false;
          this.loading.set(false);
        }),
      )
      .subscribe((response) => {
        if (!response) {
          return;
        }

        const decoded = unpack(new Uint8Array(response)) as StopsResponse;
        const options = (decoded.results ?? [])
          .filter((stop) => !stop.parent_stop_name)
          .map((stop) => ({ id: stop.stop_id, name: stop.stop_name }));

        this.parentStops.set(options);
        this.hasLoaded = true;
      });
  }
}
