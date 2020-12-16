<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3 quetz-main-table">
        <h3 class="bx--data-table-header">Jobs on the server</h3>
        <cv-data-table
          :columns="columns"
          :data="table_data"
          ref="table">
          <template slot="data">
            <cv-data-table-row v-for="(row, rowIndex) in table_data" :key="`${rowIndex}`" :value="`${rowIndex}`" :class="`${row[2]}`">
               <cv-data-table-cell >
                  <div>
                    {{ row[0] }}
                  </div>
                </cv-data-table-cell>
               <cv-data-table-cell>{{ row[1] }}</cv-data-table-cell>
               <cv-data-table-cell>{{ row[2] }}</cv-data-table-cell>
            </cv-data-table-row>
          </template>
        </cv-data-table>
    </div>
  </div>
</div>
</template>

<script>

export default {
  data: function () {
    return {
      columns: [],
      table_data: [],
      loading: true
    }
  },
  methods: {
    // TODO double request currently, also save value of #packages to display in local storage?
    load: function() {
      let url = "/api/jobs/" + this.$route.params.job_id
      return fetch(url).then((msg) => {
        return msg.json().then((decoded) => {
            console.log(decoded);
            this.columns = ["Filename", "Created", "Status"];

            let date_fn = (date) => {
              let d = new Date(date);
              return d.toLocaleDateString('en-US', {
                  day : 'numeric',
                  month : 'short',
                  year : 'numeric',
              }) + " " + d.toTimeString().slice(0, 5);
            }
            this.table_data = decoded.map((el) => [el.package_version.filename, date_fn(el.created), el.status]);
        });
      });
    },
  },
  created: function() {
    this.load()
    this.intervalID = window.setInterval(this.load, 5000);
  },
  updated() {
    this.attachEvents();
  },
  beforeDestroy() {
    window.clearInterval(this.intervalID);
  }
}
</script>

<style>
tr.success td {
  background: green !important;
  color: #111;
}
tr.failed td {
  background: red !important;
  color: #000;
}
html {
   height: 100%;
}
#app {
   min-height: 100%;
}
</style>
