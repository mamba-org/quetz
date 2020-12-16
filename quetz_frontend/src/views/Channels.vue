<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3 quetz-main-table">
        <h3 class="bx--data-table-header">Channels</h3>
        <cv-data-table
          :columns="columns"
          :data="table_data"
          :pagination="pagination"
          @search="onFilter" searchLabel="Filter" searchPlaceholder="Filter" searchClearLabel="Clear filter"
          @pagination="loadPagination"
          ref="table">
          <template slot="data">
            <cv-data-table-row v-for="(row, rowIndex) in table_data" :key="`${rowIndex}`" :value="`${rowIndex}`">
               <cv-data-table-cell>{{ row[0] }}</cv-data-table-cell>
               <cv-data-table-cell>{{ row[1] }}</cv-data-table-cell>
               <cv-data-table-cell><Password16 v-if="row[2]" class="white-svg"/></cv-data-table-cell>
            </cv-data-table-row>
          </template>
        </cv-data-table>
    </div>
  </div>
</div>
</template>

<script>
  import Password16 from '@carbon/icons-vue/es/password/16';

  export default {
    components: {
      Password16
    },
    data: function () {
      return {
        columns: [],
        table_data: [],
        loading: true,
        rowSelects: []
      }
    },
    methods: {
      loadPagination: function(args, searchquery) {
        let url = "/api/paginated/channels?"
        if (args)
        {
          this.selected_pagesize = args['length'];
          url += new URLSearchParams({
            limit: args['length'],
            skip: args['start'] - 1
          });
        }
        if (searchquery)
        {
          url += "&" + new URLSearchParams({
            q: searchquery
          })
        }
        return fetch(url).then((msg) => {
          return msg.json().then((decoded) => {
              this.columns = ["Name", "Description", "Private"];
              this.pagination = {
                numberOfItems: decoded.pagination.all_records_count,
                pageSizes: [25, 50, 100, 1000]
              };
              this.numberOfItems = decoded.pagination.all_records_count;
              this.table_data = decoded.result.map((el) => [el.name, el.description, el.private]);
          });
        });
      },
      onFilter: function(query) {
        this.loadPagination({length: 25, start: 1}, query)
      },
      attachEvents: function() {
        let router = this.$router;
        this.$el.querySelectorAll('tr').forEach((el) => {
          el.addEventListener('click', () => {
            router.push({ path: "/channel/" + this.table_data[el.getAttribute('value')][0] + "/packages"});
          });
        });
      },
    },
    created: function() {
      this.pagination = {
        numberOfItems: 0,
        pageSizes: [25, 50, 100, 1000]
      };
      this.loadPagination();
    },
    mounted() {
    },
    updated() {
      this.attachEvents();
    }
}
</script>

<style>
.white-svg {
  fill: white;
}

</style>

<style scoped>
tbody tr {
  cursor: pointer;
}
</style>